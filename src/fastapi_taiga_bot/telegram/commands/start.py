from fastapi import Depends

from fastapi_taiga_bot.telegram.commands.base import TelegramCommand
from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate

class StartCommand(TelegramCommand):
    name =  "start"
    
    def __init__(self, client: TelegramClient):
        self._client = client
    
    async def handle(self, update: TelegramUpdate, args: str):
        chat_id = update.message.chat.id
        
        if not chat_id:
            return
        
        await self._client.send_message(
            chat_id,
            "Bienvenido al bot de taiga"
        )

    def get_description(self) -> str:
        return "Inicia la conversación con el bot"


def get_start_command(
    client: TelegramClient = Depends(get_telegram_client)
    ) -> StartCommand:
    return StartCommand(client)