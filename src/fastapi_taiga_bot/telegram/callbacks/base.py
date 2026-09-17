from abc import ABC, abstractmethod

from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate


class TelegramCallback(ABC):
    data: str

    @abstractmethod
    async def handle(self, update: TelegramUpdate) -> None: ...
