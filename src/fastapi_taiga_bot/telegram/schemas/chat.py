from typing import Literal

from fastapi_taiga_bot.telegram.schemas.base import TelegramBaseModel

'''
    This is what the chat looks like in a telegram message

    {
        "id": 1111111,
        "first_name": "Joan",
        "last_name": None,
        "username": "joan_dev",
        "type": "private",
    }
'''


class TelegramChat(TelegramBaseModel):
    id: int
    type: Literal["private", "group", "supergroup", "channel"]
    first_name: str
    last_name: str | None = None
    username: str | None = None
    title: str | None = None
    