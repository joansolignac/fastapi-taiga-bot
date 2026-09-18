from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.db.engine import get_session
from fastapi_taiga_bot.telegram.commands.base import TelegramCommand
from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate
from fastapi_taiga_bot.telegram.services.message_log import log_message
from fastapi_taiga_bot.taiga.services.auth_service import (
    NotLoggedInError,
    TaigaAuthService,
    get_taiga_auth_service,
)


class PendingsCommand(TelegramCommand):
    name = "pendings"

    def __init__(self, client: TelegramClient, auth_service: TaigaAuthService, session: AsyncSession):
        self._client = client
        self._auth_service = auth_service
        self._session = session

    async def handle(self, update: TelegramUpdate, args: str) -> None:
        chat_id = update.message.chat.id

        try:
            subjects = await self._auth_service.list_pending_user_stories(self._session, chat_id)
        except NotLoggedInError:
            message_id = await self._client.send_message(
                chat_id, "Primero iniciá sesión con /login correo contraseña"
            )
            await log_message(self._session, chat_id, message_id)
            return

        if not subjects:
            message_id = await self._client.send_message(chat_id, "No tenés historias de usuario pendientes")
            await log_message(self._session, chat_id, message_id)
            return

        message_id = await self._client.send_message(chat_id, "\n".join(subjects))
        await log_message(self._session, chat_id, message_id)

    def get_description(self) -> str:
        return "Lista tus historias de usuario pendientes asignadas en Taiga"


def get_pendings_command(
    client: TelegramClient = Depends(get_telegram_client),
    auth_service: TaigaAuthService = Depends(get_taiga_auth_service),
    session: AsyncSession = Depends(get_session),
) -> PendingsCommand:
    return PendingsCommand(client, auth_service, session)
