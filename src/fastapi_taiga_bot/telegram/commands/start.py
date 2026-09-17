from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.db.engine import get_session
from fastapi_taiga_bot.telegram.commands.base import TelegramCommand
from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate
from fastapi_taiga_bot.telegram.services.menu_content import MenuContentService, get_menu_content
from fastapi_taiga_bot.taiga.models import TaigaSession

class StartCommand(TelegramCommand):
    name =  "start"

    def __init__(self, client: TelegramClient, menu_content: MenuContentService, session: AsyncSession):
        self._client = client
        self._menu_content = menu_content
        self._session = session

    async def handle(self, update: TelegramUpdate, args: str):
        chat_id = update.message.chat.id

        if not chat_id:
            return

        taiga_session = await self._session.get(TaigaSession, chat_id)
        menu = self._menu_content.build_root_menu(
            taiga_session is not None,
            taiga_session.taiga_full_name if taiga_session else None,
        )

        await self._client.send_message(chat_id, menu["text"], menu["reply_markup"])

    def get_description(self) -> str:
        return "Inicia la conversación con el bot"


def get_start_command(
    client: TelegramClient = Depends(get_telegram_client),
    menu_content: MenuContentService = Depends(get_menu_content),
    session: AsyncSession = Depends(get_session),
    ) -> StartCommand:
    return StartCommand(client, menu_content, session)
