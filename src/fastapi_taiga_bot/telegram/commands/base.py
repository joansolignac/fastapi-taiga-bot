from abc import ABC, abstractmethod

from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate

class TelegramCommand(ABC):
    name: str
    
    @abstractmethod
    async def handle(self, update: TelegramUpdate, args: str) -> None: ...
    
    @abstractmethod
    def get_description(self) -> str: ...