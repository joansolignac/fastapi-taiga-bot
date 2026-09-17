from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.db.engine import get_session
from fastapi_taiga_bot.telegram.commands.base import TelegramCommand
from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate
from fastapi_taiga_bot.taiga.services.auth_service import TaigaAuthService, get_taiga_auth_service


class LogoutCommand(TelegramCommand):
    name = "logout"

    def __init__(self, client: TelegramClient, auth_service: TaigaAuthService, session: AsyncSession):
        self._client = client
        self._auth_service = auth_service
        self._session = session

    async def handle(self, update: TelegramUpdate, args: str) -> None:
        chat_id = update.message.chat.id

        eliminada = await self._auth_service.logout(self._session, chat_id)

        if eliminada:
            await self._client.send_message(chat_id, "Sesión cerrada correctamente")
        else:
            await self._client.send_message(chat_id, "No tenías ninguna sesión iniciada")

    def get_description(self) -> str:
        return "Cierra tu sesión de Taiga"


def get_logout_command(
    client: TelegramClient = Depends(get_telegram_client),
    auth_service: TaigaAuthService = Depends(get_taiga_auth_service),
    session: AsyncSession = Depends(get_session),
) -> LogoutCommand:
    return LogoutCommand(client, auth_service, session)
