from fastapi_taiga_bot.telegram.schemas.base import TelegramBaseModel
from fastapi_taiga_bot.telegram.schemas.message import TelegramMessage

'''
    This is what an update looks like in telegram when a message is sent

    {
        "update_id": 10000,
        "message": {
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
        },
    }
'''


class TelegramUpdate(TelegramBaseModel):
    update_id: int
    message: TelegramMessage | None = None

    @property
    def is_command(self) -> bool:
        return bool(self.message and self.message.is_command)