import logging

import httpx
from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.db.engine import get_session
from fastapi_taiga_bot.telegram.commands.base import TelegramCommand
from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate
from fastapi_taiga_bot.telegram.services.menu_anchor import upsert_menu_anchor
from fastapi_taiga_bot.telegram.services.menu_content import MenuContentService, get_menu_content
from fastapi_taiga_bot.telegram.services.message_log import log_message
from fastapi_taiga_bot.taiga.services.auth_service import TaigaAuthService, get_taiga_auth_service

logger = logging.getLogger()


class LoginCommand(TelegramCommand):
    name = "login"

    def __init__(
        self,
        client: TelegramClient,
        auth_service: TaigaAuthService,
        menu_content: MenuContentService,
        session: AsyncSession,
    ):
        self._client = client
        self._auth_service = auth_service
        self._menu_content = menu_content
        self._session = session

    async def handle(
        self, update: TelegramUpdate, args: str, prompt_message_id: int | None = None
    ) -> None:
        chat_id = update.message.chat.id
        parts = args.split()

        if len(parts) != 2:
            message_id = await self._client.send_message(chat_id, "Uso: /login correo contraseña")
            await log_message(self._session, chat_id, message_id)
            return

        email, password = parts
        telegram_username = update.message.from_user.username if update.message.from_user else None

        menu = None
        try:
            display_name = await self._auth_service.login(
                self._session, chat_id, telegram_username, email, password
            )
            menu = self._menu_content.build_root_menu(True, display_name)
            mensaje = menu["text"]

            if prompt_message_id is not None:
                try:
                    await self._client.delete_message(chat_id, prompt_message_id)
                except httpx.HTTPStatusError:
                    pass  # Prompt message already gone; not worth failing the login over.
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

        message_id = await self._client.send_message(
            chat_id, mensaje, menu["reply_markup"] if menu else None
        )
        await log_message(self._session, chat_id, message_id)
        if menu is not None:
            await upsert_menu_anchor(self._session, chat_id, message_id)

    def get_description(self) -> str:
        return "Inicia sesión en Taiga: /login correo contraseña"


def get_login_command(
    client: TelegramClient = Depends(get_telegram_client),
    auth_service: TaigaAuthService = Depends(get_taiga_auth_service),
    menu_content: MenuContentService = Depends(get_menu_content),
    session: AsyncSession = Depends(get_session),
) -> LoginCommand:
    return LoginCommand(client, auth_service, menu_content, session)
