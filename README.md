# fastapi-taiga-bot

Bot de Telegram, construido sobre FastAPI, que permite a cada usuario iniciar sesión con su propia cuenta de Taiga (herramienta de gestión de proyectos) y consultar sus proyectos e historias de usuario pendientes directamente desde un menú de chat. Además, avisa automáticamente por Telegram cuando ocurren cambios relevantes en las tareas asignadas, a partir de los webhooks de Taiga.

## Funcionalidades

- Integración de Telegram implementada desde cero sobre `httpx` (basada en webhooks, sin frameworks de bots de terceros).
- Login por usuario contra Taiga (`/login`), con los tokens cifrados en Postgres — no se usa una cuenta técnica compartida.
- Menú con botones inline (`/start`), condicionado al estado de sesión:
  - Sin sesión iniciada → solo el botón "🔐 Iniciar sesión".
  - Con sesión iniciada → 🗂️ Proyectos, 📌 Pendientes, ❓ Ayuda, 🔓 Cerrar sesión.
  - "📌 Pendientes" abre un submenú con dos vistas: "📁 Por proyecto" (agrupadas por proyecto) y "⏰ Atrasadas" (con los días de atraso), cada historia con referencia, título, estado y link directo a Taiga.
- Comandos de texto equivalentes a cada opción del menú (`/login`, `/logout`, `/projects`, `/pendings`).
- Renovación automática del access token de Taiga cuando expira, sin pedirle credenciales de nuevo al usuario.
- **Notificaciones en tiempo real vía webhook de Taiga** (`POST /taiga/webhook`, firmado con HMAC-SHA1):
  - Aviso al crear una tarea y asignártela.
  - Aviso cuando cambia el estado, la fecha de entrega, o se agrega un comentario.
  - Aviso al eliminar una tarea en la que estabas asignado.
  - Al **quitar** la asignación de una tarea, el bot no solo deja de avisar de eso: **borra el mensaje original** donde te había notificado esa asignación (mismo comportamiento si te reasignan a otra persona o si la tarea se elimina directamente).
  - Los eventos repetidos (Taiga reintenta la entrega del webhook) se deduplican y se ignoran.

## Requisitos

- Python >=3.14
- [uv](https://docs.astral.sh/uv/) como gestor de paquetes
- Docker (para levantar Postgres local vía `docker compose`)
- Un túnel (ej. [ngrok](https://ngrok.com/)) para exponer el servidor local con HTTPS, necesario tanto para el webhook de Telegram como para el de Taiga

## Puesta en marcha

1. Instalar las dependencias:
   ```bash
   uv sync
   ```
2. Copiar `.env` y completar las variables necesarias (ver más abajo).
3. Levantar Postgres local:
   ```bash
   docker compose up -d
   ```
4. Aplicar las migraciones de la base de datos:
   ```bash
   uv run alembic upgrade head
   ```
5. Correr el servidor:
   ```bash
   uv run fastapi dev src/fastapi_taiga_bot/main.py
   ```
6. Exponerlo con un túnel y registrar los webhooks:
   - **Telegram**: ver `CLAUDE.md` para el comando `curl` exacto contra `setWebhook`.
   - **Taiga**: desde el proyecto en Taiga → Admin → Webhooks, agregar uno apuntando a `https://<tu-túnel>/taiga/webhook`, con la clave secreta igual a `TAIGA_WEBHOOK_SECRET`.

## Variables de entorno

| Variable | Descripción |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token obtenido de [@BotFather](https://t.me/BotFather). |
| `TELEGRAM_WEBHOOK_SECRET` | Secreto aleatorio; se valida contra el header `X-Telegram-Bot-Api-Secret-Token` en cada llamada del webhook de Telegram. |
| `TAIGA_BASE_URL` | URL base de la API REST de tu instancia de Taiga, ej. `https://taiga.example.com/api/v1`. |
| `TAIGA_WEB_BASE_URL` | URL base del frontend web de Taiga (sin `/api/v1`), usada para armar los links directos a las historias de usuario, ej. `https://taiga.example.com`. |
| `DATABASE_URL` | Cadena de conexión de Postgres con el driver async, ej. `postgresql+asyncpg://user:pass@localhost:5433/db`. |
| `TAIGA_TOKEN_ENCRYPTION_KEY` | Clave Fernet para cifrar/descifrar los tokens de Taiga guardados. Se genera con `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| `TAIGA_WEBHOOK_SECRET` | Secreto configurado en Taiga (Admin → Webhooks); Taiga firma cada payload con HMAC-SHA1 usando esta clave, y el bot valida esa firma contra el header `X-Taiga-Webhook-Signature`. |

## Comandos del bot

| Comando | Descripción |
|---|---|
| `/start` | Muestra el menú principal (según el estado de sesión). |
| `/login <email> <contraseña>` | Inicia sesión en Taiga; el mensaje con la contraseña se borra apenas se procesa, haya salido bien o mal. |
| `/logout` | Elimina la sesión de Taiga guardada. |
| `/projects` | Lista los nombres de tus proyectos de Taiga. |
| `/pendings` | Lista tus historias de usuario abiertas (no cerradas). |

## Desarrollo

Ver [CLAUDE.md](CLAUDE.md) (en inglés) para la referencia completa de arquitectura: organización de módulos, convenciones de inyección de dependencias, flujo de migraciones/base de datos, el diseño del servicio de notificaciones vía webhook de Taiga, y cómo probar los webhooks en local.

Todavía no hay tests automatizados, linter ni formatter configurados.
