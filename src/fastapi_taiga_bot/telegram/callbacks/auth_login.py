from fastapi import Depends

from fastapi_taiga_bot.telegram.callbacks.base import TelegramCallback
from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate
from fastapi_taiga_bot.telegram.services.conversation_state import (
    ConversationStateService,
    get_conversation_state,
)
from fastapi_taiga_bot.telegram.services.menu_content import MenuContentService, get_menu_content


class AuthLoginCallback(TelegramCallback):
    data = "auth:login"

    def __init__(
        self,
        client: TelegramClient,
        menu_content: MenuContentService,
        conversation_state: ConversationStateService,
    ):
        self._client = client
        self._menu_content = menu_content
        self._conversation_state = conversation_state

    async def handle(self, update: TelegramUpdate) -> None:
        message = update.callback_query.message
        chat_id = message.chat.id

        self._conversation_state.mark_awaiting_login(chat_id, message.message_id)
        menu = self._menu_content.build_login_prompt()

        await self._client.edit_message_text(
            chat_id, message.message_id, menu["text"], menu["reply_markup"]
        )


def get_auth_login_callback(
    client: TelegramClient = Depends(get_telegram_client),
    menu_content: MenuContentService = Depends(get_menu_content),
    conversation_state: ConversationStateService = Depends(get_conversation_state),
) -> AuthLoginCallback:
    return AuthLoginCallback(client, menu_content, conversation_state)
