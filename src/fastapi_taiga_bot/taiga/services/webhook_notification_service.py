import hashlib
import json
import re

import httpx
from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client
from fastapi_taiga_bot.telegram.services.message_log import log_message
from fastapi_taiga_bot.taiga.models import TaigaAssignmentNotification, TaigaSession, TaigaWebhookEvent
from fastapi_taiga_bot.taiga.services.admin_service import TaigaAdminService, get_taiga_admin_service

SUPPORTED_ACTION_PATTERN = re.compile(r"assign|status|priority|comment|update|change")


class TaigaWebhookNotificationService:
    def __init__(self, telegram_client: TelegramClient, admin_service: TaigaAdminService):
        self._telegram_client = telegram_client
        self._admin_service = admin_service

    async def process(self, session: AsyncSession, payload: dict) -> None:
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()

        session.add(TaigaWebhookEvent(fingerprint=fingerprint))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return  # Already processed this exact event before.

        action = payload.get("action")
        object_type = str(payload.get("type") or "unknown")
        object_id = (payload.get("data") or {}).get("id")
        diff = (payload.get("change") or {}).get("diff") or {} if action == "change" else {}

        if object_id is not None:
            # A deleted object has no "diff" to compare against — everyone who
            # was assigned to it loses that assignment at once.
            removed_ids = (
                self._affected_taiga_user_ids(payload) if action == "delete" else self._removed_assignee_ids(diff)
            )
            await self._delete_assignment_messages(session, object_type, object_id, removed_ids)

        # Runs before the early return below: the admin is watching the project,
        # so a story with no assignees still concerns them.
        await self._notify_admin(session, payload)

        recipient_ids = self._affected_taiga_user_ids(payload)
        if not recipient_ids or not self._is_supported(payload):
            return

        result = await session.exec(
            select(TaigaSession).where(TaigaSession.taiga_user_id.in_(recipient_ids))
        )
        recipients = result.all()

        newly_assigned_ids = recipient_ids if action == "create" else self._added_assignee_ids(diff)

        reply_markup = self._build_reply_markup(payload)
        for recipient in recipients:
            text = self._describe_action(payload, recipient.taiga_user_id, newly_assigned_ids)
            message_id = await self._telegram_client.send_message(recipient.chat_id, text, reply_markup)
            await log_message(session, recipient.chat_id, message_id)

            if object_id is not None and recipient.taiga_user_id in newly_assigned_ids:
                await self._remember_assignment_message(
                    session, object_type, object_id, recipient.taiga_user_id, recipient.chat_id, message_id
                )

    async def _notify_admin(self, session: AsyncSession, payload: dict) -> None:
        action = payload.get("action")

        if payload.get("type") != "userstory" or action not in ("create", "change"):
            return

        lines = (
            self._admin_change_lines(payload)
            if action == "change"
            else self._admin_create_lines(payload)
        )

        if not lines:
            return

        admin_user_id = await self._admin_service.get_admin_user_id()

        if (payload.get("by") or {}).get("id") == admin_user_id:
            return  # The admin's own action.

        if admin_user_id in self._affected_taiga_user_ids(payload):
            return  # They already get the regular assignee notification.

        result = await session.exec(
            select(TaigaSession).where(TaigaSession.taiga_user_id == admin_user_id)
        )
        admin_session = result.first()

        if admin_session is None:
            return  # The admin is not logged into the bot.

        message_id = await self._telegram_client.send_message(
            admin_session.chat_id, "\n\n".join(lines), self._build_reply_markup(payload)
        )
        await log_message(session, admin_session.chat_id, message_id)

    def _admin_create_lines(self, payload: dict) -> list[str]:
        author = self._display_name(payload.get("by"))
        subject, project_suffix = self._admin_subject_and_project(payload, "en el")
        line = f"✨ {author} creó la historia de usuario {subject}{project_suffix}."

        permalink = (payload.get("data") or {}).get("permalink")
        if isinstance(permalink, str) and permalink:
            line = f"{line}\n{permalink}"

        return [line]

    def _admin_change_lines(self, payload: dict) -> list[str]:
        change = payload.get("change") or {}
        diff = change.get("diff") or {}
        comment = change.get("comment")
        comment = comment.strip() if isinstance(comment, str) else ""
        status = diff.get("status") if isinstance(diff.get("status"), dict) else None

        if not comment and status is None:
            return []

        author = self._display_name(payload.get("by"))
        subject, project_suffix = self._admin_subject_and_project(payload)

        lines: list[str] = []
        if comment:
            lines.append(
                f"💬 {author} ha realizado el siguiente comentario dentro de la "
                f'historia de usuario {subject}{project_suffix}: "{comment}"'
            )
        if status is not None:
            before = status.get("from")
            after = status.get("to")
            transition = f'de "{before}" a "{after}"' if before else f'a "{after}"'
            lines.append(
                f"🔄 {author} cambió el estado de la historia de usuario "
                f"{subject}{project_suffix} {transition}."
            )
        return lines

    def _admin_subject_and_project(self, payload: dict, connector: str = "del") -> tuple[str, str]:
        subject_raw = (payload.get("data") or {}).get("subject")
        subject = f'"{subject_raw}"' if isinstance(subject_raw, str) else "una historia de usuario"
        project = self._project_label(payload)
        return subject, f' {connector} proyecto 📁 "{project}"' if project else ""

    async def _remember_assignment_message(
        self,
        session: AsyncSession,
        object_type: str,
        object_id: int,
        taiga_user_id: int,
        chat_id: int,
        message_id: int,
    ) -> None:
        result = await session.exec(
            select(TaigaAssignmentNotification).where(
                TaigaAssignmentNotification.taiga_object_type == object_type,
                TaigaAssignmentNotification.taiga_object_id == object_id,
                TaigaAssignmentNotification.taiga_user_id == taiga_user_id,
            )
        )
        existing = result.first()

        if existing is not None:
            existing.chat_id = chat_id
            existing.message_id = message_id
            session.add(existing)
        else:
            session.add(
                TaigaAssignmentNotification(
                    taiga_object_type=object_type,
                    taiga_object_id=object_id,
                    taiga_user_id=taiga_user_id,
                    chat_id=chat_id,
                    message_id=message_id,
                )
            )
        await session.commit()

    async def _delete_assignment_messages(
        self,
        session: AsyncSession,
        object_type: str,
        object_id: int,
        removed_taiga_user_ids: set[int],
    ) -> None:
        if not removed_taiga_user_ids:
            return

        result = await session.exec(
            select(TaigaAssignmentNotification).where(
                TaigaAssignmentNotification.taiga_object_type == object_type,
                TaigaAssignmentNotification.taiga_object_id == object_id,
                TaigaAssignmentNotification.taiga_user_id.in_(removed_taiga_user_ids),
            )
        )
        for notification in result.all():
            try:
                await self._telegram_client.delete_message(notification.chat_id, notification.message_id)
            except httpx.HTTPStatusError:
                pass  # Message already deleted, or too old for Telegram to delete.
            await session.delete(notification)
        await session.commit()

    def _affected_taiga_user_ids(self, payload: dict) -> set[int]:
        data = payload.get("data") or {}
        ids = [
            (data.get("assigned_to") or {}).get("id"),
            (data.get("assigned_to_extra_info") or {}).get("id"),
            *(data.get("assigned_users") or []),
        ]
        return {i for i in ids if isinstance(i, int)}

    def _added_assignee_ids(self, diff: dict) -> set[int]:
        before, after = self._assignee_diff_sets(diff)
        return after - before

    def _removed_assignee_ids(self, diff: dict) -> set[int]:
        before, after = self._assignee_diff_sets(diff)
        return before - after

    def _assignee_diff_sets(self, diff: dict) -> tuple[set[int], set[int]]:
        entry = diff.get("assigned_users")
        if entry:
            return set(entry.get("from") or []), set(entry.get("to") or [])

        entry = diff.get("assigned_to")
        if entry:
            before = entry.get("from")
            after = entry.get("to")
            return (
                {before} if isinstance(before, int) else set(),
                {after} if isinstance(after, int) else set(),
            )

        return set(), set()

    def _is_supported(self, payload: dict) -> bool:
        action = str(payload.get("action") or payload.get("type") or "").lower()
        data = payload.get("data") or {}
        return bool(
            SUPPORTED_ACTION_PATTERN.search(action)
            or data.get("comment") is not None
            or data.get("status") is not None
            or data.get("priority") is not None
        )

    def _build_reply_markup(self, payload: dict) -> dict | None:
        permalink = (payload.get("data") or {}).get("permalink")
        if not isinstance(permalink, str) or not permalink:
            return None
        return {"inline_keyboard": [[{"text": "🔗 Abrir Taiga Web", "url": permalink}]]}

    def _describe_action(
        self, payload: dict, recipient_taiga_user_id: int, newly_assigned_ids: set[int]
    ) -> str:
        action = payload.get("action") if isinstance(payload.get("action"), str) else ""
        data = payload.get("data") or {}
        subject_raw = data.get("subject")
        subject = f'"{subject_raw}"' if isinstance(subject_raw, str) else "el elemento"
        author = self._display_name(payload.get("by"))
        project = self._project_label(payload)
        project_quoted = f'"{project}"' if project else None

        if action == "create":
            return self._describe_create(payload, recipient_taiga_user_id, subject, author, project_quoted)
        if action == "delete":
            suffix = f" del proyecto 📁 {project_quoted}" if project_quoted else ""
            return f"🗑️ {author} eliminó la tarea {subject}{suffix} en la que estabas asignado."
        return self._describe_change(payload, subject, author, recipient_taiga_user_id, newly_assigned_ids, project_quoted)

    def _describe_create(
        self,
        payload: dict,
        recipient_taiga_user_id: int,
        subject: str,
        author: str,
        project_quoted: str | None,
    ) -> str:
        suffix = f" del proyecto 📁 {project_quoted}" if project_quoted else ""
        other_ids = [
            i for i in self._affected_taiga_user_ids(payload) if i != recipient_taiga_user_id
        ]

        if not other_ids:
            return f"✨ {author} creó la tarea {subject}{suffix} y te la asignó a ti."

        count = len(other_ids)
        others = "1 persona más" if count == 1 else f"{count} personas más"
        return f"✨ {author} creó la tarea {subject}{suffix} y te asignó junto con: {others}."

    def _describe_change(
        self,
        payload: dict,
        subject: str,
        author: str,
        recipient_taiga_user_id: int,
        newly_assigned_ids: set[int],
        project_quoted: str | None,
    ) -> str:
        diff = (payload.get("change") or {}).get("diff")
        if payload.get("action") != "change" or not diff:
            return self._generic_update_message(subject, project_quoted)

        project_parenthetical = f" (proyecto 📁 {project_quoted})" if project_quoted else ""
        lines: list[str] = []

        if "due_date" in diff:
            to = (diff.get("due_date") or {}).get("to")
            if isinstance(to, str) and to:
                lines.append(f"📅 Se modificó la fecha de entrega de {subject}{project_parenthetical} a {to}.")
            else:
                lines.append(f"📅 Se eliminó la fecha de entrega de {subject}{project_parenthetical}.")

        # Deliberately no message for a co-assignee unaffected by this change,
        # nor for the removed-assignment case (see #7) — that user is dropped
        # from the recipient list entirely (see _affected_taiga_user_ids), and
        # their original "you were assigned" message gets deleted instead.
        if recipient_taiga_user_id in newly_assigned_ids:
            suffix = f" del proyecto 📁 {project_quoted}" if project_quoted else ""
            lines.append(f"🔔 Te han asignado a {subject}{suffix}.")

        if "status" in diff:
            to = self._diff_display_value(diff.get("status"))
            if to:
                lines.append(f'🔄 El estado de {subject}{project_parenthetical} cambió a "{to}".')

        comment = (payload.get("change") or {}).get("comment")
        if isinstance(comment, str) and comment.strip():
            lines.append(f'💬 {author} comentó en {subject}{project_parenthetical}: "{comment.strip()}"')

        return " ".join(lines) if lines else self._generic_update_message(subject, project_quoted)

    def _generic_update_message(self, subject: str, project_quoted: str | None) -> str:
        project_parenthetical = f" (proyecto 📁 {project_quoted})" if project_quoted else ""
        return f"ℹ️ Se actualizó {subject}{project_parenthetical} sin cambios específicos detectados."

    def _project_label(self, payload: dict) -> str | None:
        # Taiga's webhook payload carries the project as a dict here; it does
        # not send the project_extra_info the REST API returns.
        project = (payload.get("data") or {}).get("project") or {}
        name = project.get("name")
        return name if isinstance(name, str) and name else None

    def _diff_display_value(self, entry) -> str | None:
        if isinstance(entry, dict):
            to = entry.get("to")
            if isinstance(to, str) and to:
                return to
        return None

    def _display_name(self, actor: dict | None) -> str:
        actor = actor or {}
        full_name = actor.get("full_name")
        if isinstance(full_name, str) and full_name:
            return full_name
        username = actor.get("username")
        if isinstance(username, str) and username:
            return username
        return "Alguien"


def get_taiga_webhook_notification_service(
    telegram_client: TelegramClient = Depends(get_telegram_client),
    admin_service: TaigaAdminService = Depends(get_taiga_admin_service),
) -> TaigaWebhookNotificationService:
    return TaigaWebhookNotificationService(telegram_client, admin_service)
