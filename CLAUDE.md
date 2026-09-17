# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A Telegram bot, built on FastAPI, that receives updates via webhook and will act as a bridge to Taiga (project management tool). The bot's own Telegram integration is implemented from scratch (no bot framework) — `python-telegram-bot` is listed as a dependency but is not currently imported anywhere in the code.

Requires Python >=3.14. Package manager is `uv`.

## Commands

```bash
# Install dependencies
uv sync

# Run the app locally (reloads on change)
uv run fastapi dev src/fastapi_taiga_bot/main.py

# Run the app as it would run in production
uv run fastapi run src/fastapi_taiga_bot/main.py

# Add a dependency
uv add <package>
```

There are no tests, linter, or formatter configured yet.

### Local webhook testing

Telegram requires an HTTPS URL for webhooks, so local testing needs a tunnel (e.g. ngrok) exposing the FastAPI server, then registering it with Telegram:

```bash
curl -X POST "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://<tunnel-domain>/telegram/webhook", "secret_token": "<TELEGRAM_WEBHOOK_SECRET>"}'
```

`secret_token` must match `TELEGRAM_WEBHOOK_SECRET` in `.env` — Telegram echoes it back on every webhook call in the `X-Telegram-Bot-Api-Secret-Token` header, which the app validates before dispatching.

## Architecture

### Configuration

`config.py` defines a single `Settings` (pydantic-settings) class reading from `.env`. It is exposed only through `get_settings()`, decorated with `@lru_cache` — never import or instantiate `Settings` directly. This keeps settings validation lazy (fails on first use, not on import) and makes the settings singleton overridable in tests via FastAPI dependency overrides.

The same lazy-singleton-via-`lru_cache` pattern is used for other shared resources (see `TelegramClient` below) instead of module-level globals — this is an intentional convention, not incidental.

### Request lifecycle (FastAPI dependency injection)

Cross-cutting concerns (auth, shared clients) are wired as FastAPI dependencies (`Depends`), not decorators or middleware classes. Dependencies are resolved in declaration order before the endpoint body runs; a dependency that raises stops the chain, which is how request rejection (e.g. an invalid webhook secret) is implemented — see `telegram/security.py`'s `verify_telegram_webhook_secret`, wired at the router level via `APIRouter(dependencies=[...])` in `telegram/router.py` so it covers every route in that router.

### `telegram/` module layout

Each integration module (currently just `telegram/`; `taiga/` is planned) follows this internal split:

- `client.py` — infrastructure: the HTTP client for the external API (Telegram Bot API), exposed via a `get_*_client()` function cached with `@lru_cache`, not a module-level instance. The client must be created lazily inside that function, never at import time (an `httpx.AsyncClient` created at import runs outside any event loop / app lifespan).
- `router.py` — FastAPI route definitions only.
- `security.py` — request-level guards (`Depends`-based validators).
- `services/` — business logic specific to this module (e.g. `dispatcher.py`, `command_parser.py`). Not to be confused with a hypothetical project-wide `core/`: logic here is coupled to this module's own schemas and is not meant to be reused by other integrations.
- `commands/` — one file per bot command, each a `TelegramCommand` subclass (see `commands/base.py`) implementing `handle()` and `get_description()`, plus a `get_<name>_command()` factory for DI. New commands must be registered in `services/dispatcher.py`'s `get_dispatcher()`.
- `schemas/` — pydantic models mirroring Telegram's webhook JSON payloads only. Parsing/business logic does not belong here (this was deliberately moved out into `services/`).

### Command dispatch flow

`POST /telegram/webhook` receives a `TelegramUpdate` → `CommandDispatcher.dispatch()` calls `command_parser.parser_command()` to extract the command name and args from the message text → looks up the registered `TelegramCommand` by name → calls its `handle()`. Unknown commands are logged and ignored; exceptions raised by a command's `handle()` are caught and logged inside the dispatcher so one failing command never breaks the webhook response.

### Adding a new integration module (e.g. `taiga/`)

Mirror the `telegram/` layout above: `client.py` for the external API client (lazy singleton via `lru_cache`), `services/` for business logic, `schemas/` for response models. Any external HTTP client should be `httpx.AsyncClient`-based to stay consistent with the rest of the codebase (avoid adding sync HTTP libraries).
