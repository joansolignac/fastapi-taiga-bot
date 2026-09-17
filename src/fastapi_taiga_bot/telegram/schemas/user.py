from fastapi_taiga_bot.telegram.schemas.base import TelegramBaseModel

'''
    This is what the user looks like in a telegram message

    {
    "id": 1111111,
    "is_bot": false,
    "first_name": "Joan",
    "last_name": null,
    "username": "joan_dev",
    "language_code": "es"
    }
'''

class TelegramUser(TelegramBaseModel):
    id: int
    is_bot: bool
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None