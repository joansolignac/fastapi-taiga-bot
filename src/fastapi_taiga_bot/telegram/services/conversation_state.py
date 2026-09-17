import time
from functools import lru_cache


class ConversationStateService:
    def __init__(self):
        self._awaiting_login: dict[int, float] = {}

    def mark_awaiting_login(self, chat_id: int, ttl_seconds: int = 300) -> None:
        self._awaiting_login[chat_id] = time.monotonic() + ttl_seconds

    def consume_awaiting_login(self, chat_id: int) -> bool:
        expires_at = self._awaiting_login.pop(chat_id, None)
        return expires_at is not None and time.monotonic() < expires_at


@lru_cache
def get_conversation_state() -> ConversationStateService:
    return ConversationStateService()
