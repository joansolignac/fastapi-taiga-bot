# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A Telegram bot, built on FastAPI, that lets each user log into their own Taiga account (project management tool) and check their projects/pending user stories from a chat menu. The bot's own Telegram integration is implemented from scratch (no bot framework) — `python-telegram-bot` is listed as a dependency but is not currently imported anywhere in the code.

Beyond per-user sessions, the bot also runs a Taiga **admin service account** (env-only credentials, no DB row) that powers two features with no per-user equivalent: a daily scheduled scan that warns assignees when a user story is close to its due date (with an inline "estoy a tiempo" / "necesito más tiempo" reply that gets posted back to Taiga as a comment), and admin-only notifications (comments, status changes, new user stories) forwarded from the Taiga webhook to whichever chat has that admin account logged in.

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

Taiga's webhook needs the same tunnel. Register it from the Taiga project's admin panel (Project → Admin → Webhooks), pointing to `https://<tunnel-domain>/taiga/webhook` with the secret key set to `TAIGA_WEBHOOK_SECRET`. Unlike Telegram's plain secret-token comparison, Taiga signs the raw request body with HMAC-SHA1 and sends it in the `X-Taiga-Webhook-Signature` header — see `taiga/security.py`'s `verify_taiga_webhook_secret`.

## Architecture

### Configuration

`config.py` defines a single `Settings` (pydantic-settings) class reading from `.env`. It is exposed only through `get_settings()`, decorated with `@lru_cache` — never import or instantiate `Settings` directly. This keeps settings validation lazy (fails on first use, not on import) and makes the settings singleton overridable in tests via FastAPI dependency overrides.

The same lazy-singleton-via-`lru_cache` pattern is used for every other shared resource instead of module-level globals (`TelegramClient`, `TaigaClient`, the SQLAlchemy `engine` in `db/engine.py`, `MenuContentService`, `ConversationStateService`) — this is an intentional convention, not incidental. A per-request resource (the DB `Session`) instead uses a plain `Depends`-injected generator (`get_session` in `db/engine.py`), never cached, since each request needs its own transactional scope.

### Request lifecycle (FastAPI dependency injection)

Cross-cutting concerns (auth, shared clients) are wired as FastAPI dependencies (`Depends`), not decorators or middleware classes. Dependencies are resolved in declaration order before the endpoint body runs; a dependency that raises stops the chain, which is how request rejection (e.g. an invalid webhook secret) is implemented — see `telegram/security.py`'s `verify_telegram_webhook_secret`, wired at the router level via `APIRouter(dependencies=[...])` in `telegram/router.py` so it covers every route in that router.

### Database (`db/`)

`db/engine.py` holds `get_engine()` (the connection pool, `@lru_cache`, created from `Settings.database_url`) and `get_session()` (an `AsyncSession` generator dependency, one per request). Migrations live in `alembic/`, configured (in `alembic/env.py`) to read the DB URL from `get_settings()` instead of `alembic.ini`, and to autogenerate against `SQLModel.metadata` (every table model must be imported there for autogenerate to see it).

### `taiga/` module — Taiga API integration, per-user sessions, admin service account, and inbound webhooks

- `client.py` — `TaigaClient`, an `httpx.AsyncClient`-based wrapper around Taiga's REST API (`login`, `refresh_token`, `me`, `list_projects`, `list_user_stories`, `list_all_open_user_stories`, `get_user_story`, `add_comment`), exposed via `get_taiga_client()` (`@lru_cache`). `list_user_stories` filters server-side by `assigned_users` + `status__is_closed=false`; `list_all_open_user_stories` is the unfiltered, cross-project variant used by the admin scan, and sends `x-disable-pagination: True` since Taiga otherwise caps a listing at 30 items. `get_user_story` + `add_comment` exist to post a comment: Taiga requires the object's current `version` (optimistic locking) on any write, so a comment is always get-then-patch, never a blind PATCH.
- `router.py` — `POST /taiga/webhook`, the inbound endpoint Taiga calls on every project event (create/change/delete on user stories, tasks, issues). Gated by `verify_taiga_webhook_secret` at the router level, same pattern as `telegram/router.py`.
- `security.py` — `verify_taiga_webhook_secret`: unlike Telegram's plain token comparison, Taiga signs the raw request body as HMAC-SHA1 and sends it in `X-Taiga-Webhook-Signature`; verified with `hmac.compare_digest`.
- `models.py` — `TaigaSession` (table `taiga_session`): one row per Telegram `chat_id`, storing the Taiga access/refresh tokens **encrypted**, never in plaintext, plus the linked `taiga_user_id` (fetched via `me()` right after login, used to match inbound webhook payloads to a chat) and `taiga_full_name` (the Taiga display name, `full_name_display` -> `full_name` -> `username`, saved by `login()` and used to greet the user in the menu). `TaigaWebhookEvent` (table `taiga_webhook_event`): a `fingerprint` (SHA-256 of the raw payload) per processed webhook, used purely for dedup — Taiga retries webhook delivery, and this makes `process()` a no-op on a repeat. `TaigaAssignmentNotification` (table `taiga_assignment_notification`): tracks the `(chat_id, message_id)` of the Telegram message that told a user "you were assigned to X", keyed by `(taiga_object_type, taiga_object_id, taiga_user_id)` — see the webhook notification flow below for why. `TaigaDueDateReminder` (table `taiga_due_date_reminder`): tracks the due-date warning sent to an assignee, keyed by `(taiga_object_id, taiga_user_id, window)` — see the due-date reminder section below.
- `services/token_cipher.py` — `TokenCipher`, Fernet-based symmetric encryption for the stored tokens (reversible — unlike password hashing, the raw token must be recoverable to reuse it against Taiga's API).
- `services/auth_service.py` — `TaigaAuthService`, the single place that: logs in and persists a session (`login`, upserts via `session.merge` since a user may re-login, and **returns the resolved `taiga_full_name`** so the caller can greet without a re-read), deletes a session (`logout`), fetches data with automatic token refresh (`list_my_projects`, `list_pending_user_stories`, `list_pending_user_stories_by_project`, `list_overdue_user_stories`, `add_comment_to_user_story` all go through a shared `_call_with_valid_token` helper that retries once after refreshing on a `401`). Raises `NotLoggedInError` when there's no session for a `chat_id` — callers catch this to gate behavior, not by checking a boolean flag first (avoids a check-then-use race). `_to_story_summary` builds the web link to a story from `taiga_web_base_url` + the project slug + the story ref — Taiga's REST payload doesn't include a ready-made web URL for user stories.
- `services/admin_service.py` — `TaigaAdminService`, a Taiga account driven entirely by `TAIGA_ADMIN_USERNAME`/`TAIGA_ADMIN_PASSWORD` env vars, exposed via `get_taiga_admin_service()` (`@lru_cache`, so its access/refresh token and resolved `taiga_user_id` live in memory for the process lifetime — no DB row, unlike a user's `TaigaSession`, since the credentials are always available to re-login from). `call_with_valid_token()` mirrors `TaigaAuthService._call_with_valid_token`'s login-then-retry-once-on-401 shape but for this single service account; `list_open_user_stories()` is the entry point the due-date scan uses to see every open story across every project, something no per-user session can do (a user's own `list_user_stories` call is scoped to their own visibility and their own `assigned_users`).
- `services/due_date_reminder_service.py` — `TaigaDueDateReminderService`. See the dedicated section below.
- `services/webhook_notification_service.py` — `TaigaWebhookNotificationService`, turns a Taiga webhook payload into Telegram messages, both to assignees and to the admin. See the dedicated section below.

### Taiga webhook → Telegram notifications (`taiga/services/webhook_notification_service.py`)

`TaigaWebhookNotificationService.process()` runs once per inbound `POST /taiga/webhook` call:

1. **Dedup**: hashes the full payload into a `fingerprint` and inserts a `TaigaWebhookEvent` row; a unique-constraint `IntegrityError` means this exact event was already processed (Taiga retries), so it returns immediately.
2. **Recipients**: `_affected_taiga_user_ids(payload)` reads the *current* state (`data.assigned_to`, `data.assigned_to_extra_info`, `data.assigned_users`) — deliberately never `old_data`, so someone who just had a task unassigned from them is not a recipient of anything new (this is what fixed the "still get notified after being unassigned" bug).
3. **Assignment-message tracking**: when the payload's `change.diff` (or, for `action == "create"`, the initial assignees) shows someone *newly* assigned (`_added_assignee_ids`), the `send_message` call's returned `message_id` is stored in `TaigaAssignmentNotification`, keyed by `(object_type, object_id, taiga_user_id)`.
4. **Assignment-message cleanup**: when someone loses an assignment — either `_removed_assignee_ids(diff)` on a `"change"` event, or, for `action == "delete"` (an object with no `diff` to compare, since it no longer exists), everyone in `_affected_taiga_user_ids(payload)` — the previously stored message for that `(object, user)` pair is deleted via `TelegramClient.delete_message` (wrapped in `try/except httpx.HTTPStatusError`, since Telegram refuses to delete messages older than ~48h) and the tracking row removed. This is deliberate: the product decision here is "delete the original assignment notification", not "send a new unassignment notification".
5. Only after steps 2–4 does it build and send the actual message text per recipient (`_describe_action`), covering `create`, `delete`, and `change` (due-date, status, comment, and the "you were newly assigned" line — never a "you were unassigned" line).

When touching this file, keep in mind `_affected_taiga_user_ids` is reused for three different purposes (who to notify, who to track an assignment message for, and — via the same current-state read — who's still assigned after a change), so a change to what it returns has wider blast radius than it looks.

**`_project_label(payload)`** reads `payload["data"]["project"]["name"]` — that's the shape Taiga's webhook actually sends (confirmed against real payloads via `GET /webhooklogs?webhook=<id>`). It does **not** read `project_extra_info`: that field is what the *REST API* (`list_user_stories`, etc.) returns, and the webhook payload leaves it `null`. Don't "fix" this back to `project_extra_info` by analogy with `auth_service.py` — the two payload shapes are genuinely different, and this was a real bug (every notification silently dropped the project name) fixed by reading the field that's actually there.

**`_notify_admin(session, payload)`** runs unconditionally on every webhook call, **before** the `recipient_ids`/`_is_supported` early return — an admin notification must fire even for a story with no assignees, which that early return would otherwise swallow. It only acts on `type == "userstory"` and `action in ("create", "change")`; other actions/types return immediately. Three guards apply to both branches: skip if the admin is the payload's own author (`payload["by"]["id"]`, resolved via `TaigaAdminService.get_admin_user_id()`), skip if the admin is already one of the affected assignees (they get the regular assignee message instead — no duplicate), and skip if there's no `TaigaSession` for the admin's `taiga_user_id` (i.e. the admin isn't logged into the bot; there's no message to send anywhere). The two branches (`_admin_create_lines` / `_admin_change_lines`) build the text independently because a `create` payload has no `change` key at all — the `change`-only early return (no comment and no status in the diff) must stay scoped to the change branch, or a `create` would be rejected by it too.

### Scheduled due-date reminders (`taiga/services/due_date_reminder_service.py`, APScheduler in `main.py`)

An `AsyncIOScheduler` (APScheduler) is started in `main.py`'s `lifespan`, running one cron job daily (`CronTrigger(hour=8, minute=0)` — a story's `due_date` is date-only, so once a day is enough) that opens its own `AsyncSession` (via `async_sessionmaker`, not `Depends`, since there's no request) and calls `TaigaDueDateReminderService.check_due_dates()`. This is the one piece of the app that runs outside the request/response cycle, so keep that in mind when touching it: DB sessions and client singletons are wired by hand instead of FastAPI DI, and a failing run is caught and logged rather than allowed to kill the scheduler.

`check_due_dates()`:

1. Fetches every open user story across every project via `TaigaAdminService.list_open_user_stories()` — the admin service account's whole reason to exist, since no single user's Taiga session can see other projects' stories.
2. For each story with a `due_date`, checks it against two fixed windows, `NOTICE_WINDOWS = (("2d", 2), ("1d", 1))` (days-before-due-date, with a short string label used for dedup).
3. For each assignee that also has a `TaigaSession` (i.e. is logged into the bot — an unidentified assignee is silently skipped), sends a message with two inline buttons, `"due:ontime"` / `"due:more_time"` (`callback_data`), then inserts a `TaigaDueDateReminder` row keyed by `(taiga_object_id, taiga_user_id, window)`. That row is what prevents a second warning for the same story-and-window on the next day's run.

`respond()` is called by the two callbacks below. It looks up the `TaigaDueDateReminder` by `(chat_id, message_id)` — not by an id embedded in `callback_data` (see the callback note below) — and if found and not already answered: posts a comment to the user story **as that user** (via `TaigaAuthService.add_comment_to_user_story`, so the comment shows up in Taiga signed by them, and if the admin is logged in, `_notify_admin` below picks it up too, with no extra code needed for that hop), then edits the Telegram message to confirm the response and remove the buttons.

`telegram/callbacks/due_date_on_time.py` / `due_date_more_time.py` are the two callbacks registered for `"due:ontime"` / `"due:more_time"`. They're the one place in `callbacks/` whose `callback_data` doesn't carry a per-object id — `CallbackDispatcher` only does exact-string dict lookup and rejects duplicate `data` values, so a dynamic id would need a different dispatch mechanism entirely. Resolving the pending reminder by `(chat_id, message_id)` from `update.callback_query.message` sidesteps that without touching the dispatcher.

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

`build_root_menu(is_logged_in, display_name=None)` takes an optional `display_name` (defaults to `None` so none of the call sites that pass `False`/no session need updating) and only affects the logged-in branch's greeting line. Of the several call sites, only the two that render the *logged-in* menu with an actual `TaigaSession` in hand — `telegram/commands/start.py` and `telegram/callbacks/menu_root.py` — pass `taiga_session.taiga_full_name`; every other call site (logout, `NotLoggedInError` fallbacks, etc.) renders the logged-out menu and doesn't need a name. `LoginCommand` (`telegram/commands/login.py`) also renders the logged-in menu directly on a successful login — using the display name `TaigaAuthService.login()` returns — instead of the old plain-text "sesión iniciada" message, so the menu opens automatically right after `/login` (both the slash-command path and the "awaiting credentials" conversational path, since both end up in the same `handle()`). The `finally` block that deletes the plaintext-password message is untouched by this — see the security note below.

"📌 Pendientes" (`menu:pendings`) is itself a submenu, not a direct listing: it only renders two buttons, "📁 Por proyecto" (`menu:pendings:by_project`) and "⏰ Atrasadas" (`menu:pendings:overdue`), each backed by its own callback (`menu_pendings_by_project.py`, `menu_pendings_overdue.py`) and its own `TaigaAuthService` method. This mirrors the `/pendings` slash command's data (`list_pending_user_stories`) but grouped/filtered differently — the three methods intentionally each make their own `list_user_stories` call rather than sharing one, consistent with the rest of `auth_service.py`.

### Adding a new command or callback

- New slash command: add `commands/<name>.py` (`TelegramCommand` subclass + `get_<name>_command()`), register in `services/dispatcher.py`'s `get_dispatcher()`.
- New menu button: add `callbacks/<name>.py` (`TelegramCallback` subclass + `get_<name>_callback()`), register in `services/callback_dispatcher.py`'s `get_callback_dispatcher()`, and add the button (with its `callback_data`) to the relevant `MenuContentService.build_*` method.
- If it needs to read/write the Taiga session, inject `TaigaAuthService` (business logic) and `AsyncSession` (only if querying `TaigaSession` directly, e.g. to check login state) via `Depends` — don't call `TaigaClient` directly from a command/callback.

### Security notes worth preserving

- Webhook secret/signature comparison (`telegram/security.py`'s plain token check, `taiga/security.py`'s HMAC-SHA1 signature check) and token encryption (`taiga/services/token_cipher.py`) exist specifically to avoid failure modes already hit during development: an unauthenticated party posting fake Telegram updates or fake Taiga webhook events, and Taiga credentials being recoverable from a database dump. Don't replace `compare_digest`-style comparisons with `==`, and don't switch token storage from encryption to hashing (hashing is one-way; the raw token must be recoverable to reuse it against Taiga's API).
- `/login`'s handler always deletes the triggering message (`finally` block) whether login succeeds or fails, because it contains the password in plaintext — preserve this when touching that command.
