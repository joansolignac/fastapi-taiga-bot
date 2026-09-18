from datetime import date
from functools import lru_cache

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.config import get_settings
from fastapi_taiga_bot.taiga.models import TaigaDueDateReminder, TaigaSession
from fastapi_taiga_bot.taiga.services.admin_service import TaigaAdminService, get_taiga_admin_service
from fastapi_taiga_bot.taiga.client import get_taiga_client
from fastapi_taiga_bot.taiga.services.auth_service import TaigaAuthService
from fastapi_taiga_bot.taiga.services.date_formatting import format_relative_due_date
from fastapi_taiga_bot.taiga.services.token_cipher import get_token_cipher
from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client
from fastapi_taiga_bot.telegram.services.menu_anchor import refresh_menu_anchor
from fastapi_taiga_bot.telegram.services.menu_content import MenuContentService, get_menu_content

# (label stored for dedup, days before the due date that triggers the warning)
NOTICE_WINDOWS = (("2d", 2), ("1d", 1), ("0d", 0))

RESPONSE_COMMENTS = {
    "on_time": "Estoy a tiempo con esta historia de usuario.",
    "needs_more_time": "Necesito más tiempo para esta historia de usuario.",
}

RESPONSE_CONFIRMATIONS = {
    "on_time": "✅ Registrado: estás a tiempo.",
    "needs_more_time": "⏳ Registrado: necesitas más tiempo.",
}


class TaigaDueDateReminderService:
    def __init__(
        self,
        admin_service: TaigaAdminService,
        auth_service: TaigaAuthService,
        telegram_client: TelegramClient,
        menu_content: MenuContentService,
    ):
        self._admin_service = admin_service
        self._auth_service = auth_service
        self._telegram_client = telegram_client
        self._menu_content = menu_content

    async def check_due_dates(self, session: AsyncSession) -> None:
        stories = await self._admin_service.list_open_user_stories()

        result = await session.exec(select(TaigaSession))
        sessions_by_taiga_user_id = {
            taiga_session.taiga_user_id: taiga_session for taiga_session in result.all()
        }
        if not sessions_by_taiga_user_id:
            return

        today = date.today()
        notified_sessions: dict[int, TaigaSession] = {}
        for story in stories:
            due_date = story.get("due_date")
            if not due_date:
                continue

            days_until = (date.fromisoformat(due_date) - today).days
            for window, threshold in NOTICE_WINDOWS:
                if days_until != threshold:
                    continue

                for taiga_user_id in self._assignee_ids(story):
                    taiga_session = sessions_by_taiga_user_id.get(taiga_user_id)
                    if taiga_session is None:
                        continue  # Assignee is not identified in the bot.
                    if await self._notify(session, story, taiga_session, window):
                        notified_sessions[taiga_session.chat_id] = taiga_session

        for chat_id, taiga_session in notified_sessions.items():
            await refresh_menu_anchor(
                session, self._telegram_client, self._menu_content, chat_id,
                True, taiga_session.taiga_full_name,
            )

    async def respond(
        self, session: AsyncSession, chat_id: int, message_id: int, response: str
    ) -> None:
        result = await session.exec(
            select(TaigaDueDateReminder).where(
                TaigaDueDateReminder.chat_id == chat_id,
                TaigaDueDateReminder.message_id == message_id,
            )
        )
        reminder = result.first()

        if reminder is None or reminder.responded:
            return

        # Commented as the user themselves, so Taiga attributes it to them and
        # the resulting webhook is what notifies the admin. Done before marking
        # the reminder so a Taiga failure leaves the buttons usable for a retry.
        await self._auth_service.add_comment_to_user_story(
            session, chat_id, reminder.taiga_object_id, RESPONSE_COMMENTS[response]
        )

        reminder.responded = True
        reminder.response = response
        session.add(reminder)
        await session.commit()

        await self._telegram_client.edit_message_text(
            chat_id,
            message_id,
            RESPONSE_CONFIRMATIONS[response],
            {"inline_keyboard": []},
        )

    async def _notify(
        self,
        session: AsyncSession,
        story: dict,
        taiga_session: TaigaSession,
        window: str,
    ) -> bool:
        result = await session.exec(
            select(TaigaDueDateReminder).where(
                TaigaDueDateReminder.taiga_object_id == story["id"],
                TaigaDueDateReminder.taiga_user_id == taiga_session.taiga_user_id,
                TaigaDueDateReminder.window == window,
            )
        )
        if result.first() is not None:
            return False  # Already warned for this story and window.

        message_id = await self._telegram_client.send_message(
            taiga_session.chat_id, self._build_text(story), self._build_reply_markup()
        )

        session.add(
            TaigaDueDateReminder(
                taiga_object_id=story["id"],
                taiga_user_id=taiga_session.taiga_user_id,
                chat_id=taiga_session.chat_id,
                message_id=message_id,
                window=window,
            )
        )
        await session.commit()
        return True

    async def send_or_refresh_overdue_reminders(
        self,
        session: AsyncSession,
        chat_id: int,
        taiga_user_id: int,
        stories: list[dict],
    ) -> list[dict]:
        """For each overdue story (auth_service story-summary dicts: id, ref,
        subject, status, project_name, url, due_date): if the user already
        responded to a prior "overdue" reminder for it, leave it alone (no
        Telegram traffic) and mark it responded. Otherwise delete any
        previous unresponded reminder message for that story and send a
        fresh one — with the on-time/more-time buttons — so the day count
        shown stays current. Returns `stories` with `responded`/`response`
        added to each item, for the caller to render a summary."""
        enriched: list[dict] = []
        for story in stories:
            result = await session.exec(
                select(TaigaDueDateReminder).where(
                    TaigaDueDateReminder.taiga_object_id == story["id"],
                    TaigaDueDateReminder.taiga_user_id == taiga_user_id,
                    TaigaDueDateReminder.window == "overdue",
                )
            )
            reminder = result.first()

            if reminder is not None and reminder.responded:
                enriched.append({**story, "responded": True, "response": reminder.response})
                continue

            if reminder is not None:
                try:
                    await self._telegram_client.delete_message(chat_id, reminder.message_id)
                except httpx.HTTPStatusError:
                    pass  # Already gone, or too old to delete — send the fresh one regardless.

            message_id = await self._telegram_client.send_message(
                chat_id, self._build_text(story), self._build_reply_markup()
            )

            if reminder is not None:
                reminder.chat_id = chat_id
                reminder.message_id = message_id
                session.add(reminder)
            else:
                session.add(
                    TaigaDueDateReminder(
                        taiga_object_id=story["id"],
                        taiga_user_id=taiga_user_id,
                        chat_id=chat_id,
                        message_id=message_id,
                        window="overdue",
                    )
                )
            await session.commit()

            enriched.append({**story, "responded": False, "response": None})

        return enriched

    def _assignee_ids(self, story: dict) -> set[int]:
        ids = [*(story.get("assigned_users") or []), story.get("assigned_to")]
        return {i for i in ids if isinstance(i, int)}

    def _build_text(self, story: dict) -> str:
        project_info = story.get("project_extra_info")
        if project_info:
            # Raw Taiga API/webhook shape (used by the daily cron scan).
            project_name = project_info.get("name")
            url = f"{get_settings().taiga_web_base_url.rstrip('/')}/project/{project_info.get('slug')}/us/{story['ref']}"
        else:
            # auth_service story-summary shape (used by the on-demand "Atrasadas" menu).
            project_name = story.get("project_name")
            url = story.get("url")

        when = format_relative_due_date(date.fromisoformat(story["due_date"]))

        return (
            f"⏰ La historia de usuario #{story['ref']} \"{story['subject']}\" "
            f"del proyecto 📁 \"{project_name}\" {when}.\n\n"
            f"{url}\n\n"
            "¿Cómo vas con esta tarea?"
        )

    def _build_reply_markup(self) -> dict:
        return {
            "inline_keyboard": [
                [
                    {"text": "👍 Estoy a tiempo", "callback_data": "due:ontime"},
                    {"text": "⏳ Necesito más tiempo", "callback_data": "due:more_time"},
                ]
            ]
        }


@lru_cache
def get_taiga_due_date_reminder_service() -> TaigaDueDateReminderService:
    auth_service = TaigaAuthService(get_taiga_client(), get_token_cipher())
    return TaigaDueDateReminderService(
        get_taiga_admin_service(), auth_service, get_telegram_client(), get_menu_content()
    )
