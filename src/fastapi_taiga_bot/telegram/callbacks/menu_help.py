from fastapi import Depends

from fastapi_taiga_bot.telegram.callbacks.base import TelegramCallback
from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate
from fastapi_taiga_bot.telegram.services.dispatcher import CommandDispatcher, get_dispatcher
from fastapi_taiga_bot.telegram.services.menu_content import MenuContentService, get_menu_content


class MenuHelpCallback(TelegramCallback):
    data = "menu:help"

    def __init__(self, client: TelegramClient, menu_content: MenuContentService, dispatcher: CommandDispatcher):
        self._client = client
        self._menu_content = menu_content
        self._dispatcher = dispatcher

    async def handle(self, update: TelegramUpdate) -> None:
        message = update.callback_query.message
        chat_id = message.chat.id

        commands = [(c.name, c.get_description()) for c in self._dispatcher.get_commands()]
        menu = self._menu_content.build_help_menu(commands)

        await self._client.edit_message_text(
            chat_id, message.message_id, menu["text"], menu["reply_markup"]
        )


def get_menu_help_callback(
    client: TelegramClient = Depends(get_telegram_client),
    menu_content: MenuContentService = Depends(get_menu_content),
    dispatcher: CommandDispatcher = Depends(get_dispatcher),
) -> MenuHelpCallback:
    return MenuHelpCallback(client, menu_content, dispatcher)
