from datetime import datetime

from pydantic import Field

from fastapi_taiga_bot.telegram.schemas.base import TelegramBaseModel
from fastapi_taiga_bot.telegram.schemas.user import TelegramUser
from fastapi_taiga_bot.telegram.schemas.chat import TelegramChat

'''
    This is what the message looks like in a telegram update

    {
        "message_id": 1365,
        "from": {
            "id": 1111111,
            "is_bot": False,
            "first_name": "Joan",
            "last_name": None,
            "username": "joan_dev",
            "language_code": "es",
        },
        "chat": {
            "id": 1111111,
            "first_name": "Joan",
            "last_name": None,
            "username": "joan_dev",
            "type": "private",
        },
        "date": 1699999999,
        "text": "/start",
    }
'''


class TelegramMessage(TelegramBaseModel):
    message_id: int
    from_user: TelegramUser | None = Field(default=None, alias="from")
    chat: TelegramChat
    date: datetime
    text: str | None = None
    
    @property
    def is_command(self) -> bool:
        return bool(self.text and self.text.startswith("/"))