from datetime import date
from functools import lru_cache

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.config import get_settings
from fastapi_taiga_bot.taiga.models import TaigaDueDateReminder, TaigaSession
from fastapi_taiga_bot.taiga.services.admin_service import TaigaAdminService, get_taiga_admin_service
from fastapi_taiga_bot.taiga.client import get_taiga_client
from fastapi_taiga_bot.taiga.services.auth_service import TaigaAuthService
from fastapi_taiga_bot.taiga.services.token_cipher import get_token_cipher
from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client

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
    ):
        self._admin_service = admin_service
        self._auth_service = auth_service
        self._telegram_client = telegram_client

    async def check_due_dates(self, session: AsyncSession) -> None:
        stories = await self._admin_service.list_open_user_stories()

        result = await session.exec(select(TaigaSession))
        sessions_by_taiga_user_id = {
            taiga_session.taiga_user_id: taiga_session for taiga_session in result.all()
        }
        if not sessions_by_taiga_user_id:
            return

        today = date.today()
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
                    await self._notify(session, story, taiga_session, window)

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
    ) -> None:
        result = await session.exec(
            select(TaigaDueDateReminder).where(
                TaigaDueDateReminder.taiga_object_id == story["id"],
                TaigaDueDateReminder.taiga_user_id == taiga_session.taiga_user_id,
                TaigaDueDateReminder.window == window,
            )
        )
        if result.first() is not None:
            return  # Already warned for this story and window.

        message_id = await self._telegram_client.send_message(
            taiga_session.chat_id, self._build_text(story, window), self._build_reply_markup()
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

    def _assignee_ids(self, story: dict) -> set[int]:
        ids = [*(story.get("assigned_users") or []), story.get("assigned_to")]
        return {i for i in ids if isinstance(i, int)}

    def _build_text(self, story: dict, window: str) -> str:
        project_info = story.get("project_extra_info") or {}
        web_base_url = get_settings().taiga_web_base_url.rstrip("/")
        url = f"{web_base_url}/project/{project_info.get('slug')}/us/{story['ref']}"
        when = "vence HOY" if window == "0d" else f"vence el {story['due_date']}"

        return (
            f"⏰ La historia de usuario #{story['ref']} \"{story['subject']}\" "
            f"del proyecto 📁 \"{project_info.get('name')}\" {when}.\n\n"
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
        get_taiga_admin_service(), auth_service, get_telegram_client()
    )
