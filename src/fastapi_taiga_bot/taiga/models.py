from datetime import datetime

from sqlalchemy import BigInteger, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


class TaigaSession(SQLModel, table=True):
    __tablename__ = "taiga_session"

    # Telegram chat_ids can exceed the range of a 32-bit INTEGER,
    # so they're mapped to BIGINT explicitly instead of SQLModel's default.
    chat_id: int = Field(sa_column=Column(BigInteger, primary_key=True, autoincrement=False))
    telegram_username: str | None = None
    taiga_full_name: str | None = None
    taiga_user_id: int | None = Field(default=None, index=True)
    access_token_encrypted: str
    refresh_token_encrypted: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaigaWebhookEvent(SQLModel, table=True):
    __tablename__ = "taiga_webhook_event"

    id: int | None = Field(default=None, primary_key=True)
    fingerprint: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaigaAssignmentNotification(SQLModel, table=True):
    """Tracks the Telegram message that told a user they were assigned to a
    Taiga object, so it can be deleted if that assignment is later removed."""

    __tablename__ = "taiga_assignment_notification"
    __table_args__ = (
        UniqueConstraint(
            "taiga_object_type", "taiga_object_id", "taiga_user_id",
            name="uq_taiga_assignment_notification_object_user",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    taiga_object_type: str
    taiga_object_id: int
    taiga_user_id: int = Field(index=True)
    chat_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    message_id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaigaDueDateReminder(SQLModel, table=True):
    """Tracks the Telegram message warning a user that a user story is about to
    be due. The unique key is what keeps a task+window from being warned twice."""

    __tablename__ = "taiga_due_date_reminder"
    __table_args__ = (
        UniqueConstraint(
            "taiga_object_id", "taiga_user_id", "window",
            name="uq_taiga_due_date_reminder_object_user_window",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    taiga_object_id: int
    taiga_user_id: int = Field(index=True)
    chat_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    message_id: int
    window: str
    responded: bool = Field(default=False)
    response: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
