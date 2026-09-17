import time
from functools import lru_cache
from typing import NamedTuple


class AwaitingLogin(NamedTuple):
    expires_at: float
    prompt_message_id: int


class ConversationStateService:
    def __init__(self):
        self._awaiting_login: dict[int, AwaitingLogin] = {}

    def mark_awaiting_login(self, chat_id: int, prompt_message_id: int, ttl_seconds: int = 300) -> None:
        self._awaiting_login[chat_id] = AwaitingLogin(time.monotonic() + ttl_seconds, prompt_message_id)

    def consume_awaiting_login(self, chat_id: int) -> int | None:
        entry = self._awaiting_login.pop(chat_id, None)
        if entry is None or time.monotonic() >= entry.expires_at:
            return None
        return entry.prompt_message_id


@lru_cache
def get_conversation_state() -> ConversationStateService:
    return ConversationStateService()
