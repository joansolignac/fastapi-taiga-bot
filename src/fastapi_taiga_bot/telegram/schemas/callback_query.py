from pydantic import Field

from fastapi_taiga_bot.telegram.schemas.base import TelegramBaseModel
from fastapi_taiga_bot.telegram.schemas.message import TelegramMessage
from fastapi_taiga_bot.telegram.schemas.user import TelegramUser


class TelegramCallbackQuery(TelegramBaseModel):
    id: str
    from_user: TelegramUser = Field(alias="from")
    message: TelegramMessage | None = None
    data: str | None = None
