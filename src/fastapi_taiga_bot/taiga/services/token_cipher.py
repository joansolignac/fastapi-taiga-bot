from functools import lru_cache

from cryptography.fernet import Fernet

from fastapi_taiga_bot.config import get_settings


class TokenCipher:
    def __init__(self):
        self._fernet = Fernet(get_settings().taiga_token_encryption_key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode()).decode()


@lru_cache
def get_token_cipher() -> TokenCipher:
    return TokenCipher()
