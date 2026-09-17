# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A Telegram bot, built on FastAPI, that lets each user log into their own Taiga account (project management tool) and check their projects/pending user stories from a chat menu. The bot's own Telegram integration is implemented from scratch (no bot framework) — `python-telegram-bot` is listed as a dependency but is not currently imported anywhere in the code.

Requires Python >=3.14. Package manager is `uv`. Postgres runs locally via `docker compose`.

## Commands

```bash
# Install dependencies
uv sync

# Start local Postgres (docker-compose.yml service `postgres`, host port 5433)
docker compose up -d

# Apply database migrations
uv run alembic upgrade head

# Generate a new migration after changing a SQLModel table
uv run alembic revision --autogenerate -m "description"
# Always inspect the generated file before applying it:
# - add `import sqlmodel` manually (autogenerate omits it, a known SQLModel/Alembic quirk)
# - integer primary keys that are NOT meant to auto-increment (e.g. an externally-provided
#   id like a Telegram chat_id) need `autoincrement=False` and, if they can exceed 2^31,
#   an explicit `sa_column=Column(BigInteger, ...)` on the model field

# Run the app locally (reloads on change)
uv run fastapi dev src/fastapi_taiga_bot/main.py

# Run the app as it would run in production (no auto-reload — see note below)
uv run fastapi run src/fastapi_taiga_bot/main.py

# Add a dependency
uv add <package>
```

There are no tests, linter, or formatter configured yet.

**`fastapi dev`'s auto-reload can silently drop in-flight requests.** If a file changes while a slow request (e.g. `/login`, which calls the Taiga API before writing to the database) is being processed, the reloader kills and restarts the server process mid-request — no exception, no response, and no database write. When debugging a request that seems to vanish with no error, restart with `fastapi run` (no reload) to rule this out before suspecting application code.

### Local webhook testing

Telegram requires an HTTPS URL for webhooks, so local testing needs a tunnel (e.g. ngrok) exposing the FastAPI server, then registering it with Telegram:

```bash
curl -X POST "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://<tunnel-domain>/telegram/webhook", "secret_token": "<TELEGRAM_WEBHOOK_SECRET>"}'
```

`secret_token` must match `TELEGRAM_WEBHOOK_SECRET` in `.env` — Telegram echoes it back on every webhook call in the `X-Telegram-Bot-Api-Secret-Token` header, which the app validates before dispatching. Check delivery status/errors any time with `getWebhookInfo`:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

## Architecture

### Configuration

`config.py` defines a single `Settings` (pydantic-settings) class reading from `.env`. It is exposed only through `get_settings()`, decorated with `@lru_cache` — never import or instantiate `Settings` directly. This keeps settings validation lazy (fails on first use, not on import) and makes the settings singleton overridable in tests via FastAPI dependency overrides.

The same lazy-singleton-via-`lru_cache` pattern is used for every other shared resource instead of module-level globals (`TelegramClient`, `TaigaClient`, the SQLAlchemy `engine` in `db/engine.py`, `MenuContentService`, `ConversationStateService`) — this is an intentional convention, not incidental. A per-request resource (the DB `Session`) instead uses a plain `Depends`-injected generator (`get_session` in `db/engine.py`), never cached, since each request needs its own transactional scope.

### Request lifecycle (FastAPI dependency injection)

Cross-cutting concerns (auth, shared clients) are wired as FastAPI dependencies (`Depends`), not decorators or middleware classes. Dependencies are resolved in declaration order before the endpoint body runs; a dependency that raises stops the chain, which is how request rejection (e.g. an invalid webhook secret) is implemented — see `telegram/security.py`'s `verify_telegram_webhook_secret`, wired at the router level via `APIRouter(dependencies=[...])` in `telegram/router.py` so it covers every route in that router.

### Database (`db/`)

`db/engine.py` holds `get_engine()` (the connection pool, `@lru_cache`, created from `Settings.database_url`) and `get_session()` (an `AsyncSession` generator dependency, one per request). Migrations live in `alembic/`, configured (in `alembic/env.py`) to read the DB URL from `get_settings()` instead of `alembic.ini`, and to autogenerate against `SQLModel.metadata` (every table model must be imported there for autogenerate to see it).

### `taiga/` module — Taiga API integration and per-user sessions

- `client.py` — `TaigaClient`, an `httpx.AsyncClient`-based wrapper around Taiga's REST API (`login`, `refresh_token`, `me`, `list_projects`, `list_user_stories`), exposed via `get_taiga_client()` (`@lru_cache`).
- `models.py` — `TaigaSession` (SQLModel table `taiga_session`): one row per Telegram `chat_id`, storing the Taiga access/refresh tokens **encrypted**, never in plaintext.
- `services/token_cipher.py` — `TokenCipher`, Fernet-based symmetric encryption for the stored tokens (reversible — unlike password hashing, the raw token must be recoverable to reuse it against Taiga's API).
- `services/auth_service.py` — `TaigaAuthService`, the single place that: logs in and persists a session (`login`, upserts via `session.merge`, since a user may re-login), deletes a session (`logout`), and fetches data with automatic token refresh (`list_my_projects`, `list_pending_user_stories` both go through a shared `_call_with_valid_token` helper that retries once after refreshing on a `401`). Raises `NotLoggedInError` when there's no session for a `chat_id` — callers catch this to gate behavior, not by checking a boolean flag first (avoids a check-then-use race).

### `telegram/` module layout

Each integration module (`telegram/`, `taiga/`) follows this internal split:

- `client.py` — infrastructure: the HTTP client for the external API, exposed via a `get_*_client()` function cached with `@lru_cache`, not a module-level instance. The client must be created lazily inside that function, never at import time (an `httpx.AsyncClient` created at import runs outside any event loop / app lifespan).
- `router.py` — FastAPI route definitions only. The single `POST /telegram/webhook` route branches on `update.is_callback` to send the update to either the command pipeline or the callback pipeline (see below).
- `security.py` — request-level guards (`Depends`-based validators).
- `services/` — business logic specific to this module. Not to be confused with a hypothetical project-wide `core/`: logic here is coupled to this module's own schemas and is not meant to be reused by other integrations.
- `commands/` — one file per **slash command**, each a `TelegramCommand` subclass (`commands/base.py`) implementing `handle()` and `get_description()`, plus a `get_<name>_command()` factory for DI. New commands must be registered in `services/dispatcher.py`'s `get_dispatcher()`.
- `callbacks/` — one file per **inline-keyboard button**, each a `TelegramCallback` subclass (`callbacks/base.py`) implementing `handle(update)`, plus a `get_<name>_callback()` factory. Registered in `services/callback_dispatcher.py`'s `get_callback_dispatcher()`. Symmetric to `commands/`, but keyed by `callback_data` instead of a command name, and responds via `edit_message_text` (in place) instead of `send_message` (new message).
- `schemas/` — pydantic models mirroring Telegram's webhook JSON payloads only. Parsing/business logic does not belong here (this was deliberately moved out into `services/`).

### Two dispatch pipelines: commands vs. callbacks

`POST /telegram/webhook` receives a `TelegramUpdate`, which can carry either a `message` or a `callback_query` (never both):

- **Commands** (`update.message`, text starting with `/`) → `CommandDispatcher.dispatch()` (`services/dispatcher.py`) calls `command_parser.parser_command()` to extract the command name and args → looks up the registered `TelegramCommand` by name → calls its `handle()`.
- **Callbacks** (`update.callback_query`, sent when a user taps an inline button) → `CallbackDispatcher.dispatch()` (`services/callback_dispatcher.py`) looks up the registered `TelegramCallback` by `callback_query.data` → calls its `handle()` → **always** calls `answer_callback_query` afterward (in a `finally`), regardless of outcome — Telegram requires this or the tapped button's loading spinner never stops.
- **Plain text while awaiting login** — a third case handled inside `CommandDispatcher.dispatch()` itself (checked first, before command parsing): if a message is plain text (not a command) and `ConversationStateService.consume_awaiting_login(chat_id)` returns `True` (set when the user taps "🔐 Iniciar sesión"), the text is routed straight into the existing `LoginCommand.handle(update, text)` — the exact same code path as `/login <email> <password>`. This is the one deliberate exception to "commands are matched by name": it lets a button press collect free-text credentials without a second command-handling abstraction, and without duplicating `LoginCommand`'s logic.

Both dispatchers log-and-continue on a handler exception — one failing command/callback never breaks the webhook response (which always returns `{"ok": true}`).

### Menu system (`services/menu_content.py`, `services/conversation_state.py`)

`MenuContentService` is the single source of truth for every menu's text + `inline_keyboard`, keyed by login state (`session.get(TaigaSession, chat_id) is not None`, checked directly — there's no separate "is logged in" boolean flag). `/start` and the `menu:root` callback both render through it, so the two entry points (typing `/start` vs. tapping "⬅️ Volver") never drift out of sync. `ConversationStateService` is a small in-memory (not DB-backed) TTL map — fine for a short-lived "awaiting credentials" window; it does not need to survive a restart.

### Adding a new command or callback

- New slash command: add `commands/<name>.py` (`TelegramCommand` subclass + `get_<name>_command()`), register in `services/dispatcher.py`'s `get_dispatcher()`.
- New menu button: add `callbacks/<name>.py` (`TelegramCallback` subclass + `get_<name>_callback()`), register in `services/callback_dispatcher.py`'s `get_callback_dispatcher()`, and add the button (with its `callback_data`) to the relevant `MenuContentService.build_*` method.
- If it needs to read/write the Taiga session, inject `TaigaAuthService` (business logic) and `AsyncSession` (only if querying `TaigaSession` directly, e.g. to check login state) via `Depends` — don't call `TaigaClient` directly from a command/callback.

### Security notes worth preserving

- Webhook secret comparison (`security.py`) and token encryption (`taiga/services/token_cipher.py`) exist specifically to avoid two failure modes already hit during development: an unauthenticated party posting fake Telegram updates, and Taiga credentials being recoverable from a database dump. Don't replace `secrets.compare_digest`-style comparisons with `==`, and don't switch token storage from encryption to hashing (hashing is one-way; the raw token must be recoverable to reuse it against Taiga's API).
- `/login`'s handler always deletes the triggering message (`finally` block) whether login succeeds or fails, because it contains the password in plaintext — preserve this when touching that command.
