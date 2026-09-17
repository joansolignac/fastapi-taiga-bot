import logging

import httpx
from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.db.engine import get_session
from fastapi_taiga_bot.telegram.commands.base import TelegramCommand
from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate
from fastapi_taiga_bot.taiga.services.auth_service import TaigaAuthService, get_taiga_auth_service

logger = logging.getLogger()


class LoginCommand(TelegramCommand):
    name = "login"

    def __init__(self, client: TelegramClient, auth_service: TaigaAuthService, session: AsyncSession):
        self._client = client
        self._auth_service = auth_service
        self._session = session

    async def handle(self, update: TelegramUpdate, args: str) -> None:
        chat_id = update.message.chat.id
        parts = args.split()

        if len(parts) != 2:
            await self._client.send_message(chat_id, "Uso: /login correo contraseña")
            return

        email, password = parts
        telegram_username = update.message.from_user.username if update.message.from_user else None

        try:
            await self._auth_service.login(self._session, chat_id, telegram_username, email, password)
            mensaje = "Sesión iniciada correctamente"
        except httpx.HTTPStatusError:
            mensaje = "No se pudo iniciar sesión, revisá tus credenciales"
        except Exception:
            # Any other failure (unexpected response shape, DB error, etc.) must still
            # reach the user — silently swallowing it here would leave them thinking
            # nothing happened, while the password message below still gets deleted.
            logger.exception("Unexpected error while logging in")
            mensaje = "Ocurrió un error inesperado al iniciar sesión, intentá de nuevo"
        finally:
            # The original message has the password in plain text — it's deleted
            # regardless of whether login succeeded, to avoid leaving it visible in the chat.
            await self._client.delete_message(chat_id, update.message.message_id)

        await self._client.send_message(chat_id, mensaje)

    def get_description(self) -> str:
        return "Inicia sesión en Taiga: /login correo contraseña"


def get_login_command(
    client: TelegramClient = Depends(get_telegram_client),
    auth_service: TaigaAuthService = Depends(get_taiga_auth_service),
    session: AsyncSession = Depends(get_session),
) -> LoginCommand:
    return LoginCommand(client, auth_service, session)
