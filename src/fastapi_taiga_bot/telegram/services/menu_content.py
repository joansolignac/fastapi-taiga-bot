from functools import lru_cache

BACK_BUTTON = {"text": "⬅️ Volver", "callback_data": "menu:root"}


class MenuContentService:
    def build_root_menu(self, is_logged_in: bool) -> dict:
        if not is_logged_in:
            return {
                "text": "👋 ¡Bienvenido al bot de Taiga!\n\n🔐 Iniciá sesión para ver tus proyectos y pendientes.",
                "reply_markup": {
                    "inline_keyboard": [[{"text": "🔐 Iniciar sesión", "callback_data": "auth:login"}]]
                },
            }

        return {
            "text": "👋 ¡Bienvenido! Elegí una opción:",
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": "🗂️ Proyectos", "callback_data": "menu:projects"}],
                    [{"text": "📌 Pendientes", "callback_data": "menu:pendings"}],
                    [{"text": "❓ Ayuda", "callback_data": "menu:help"}],
                    [{"text": "🔓 Cerrar sesión", "callback_data": "auth:logout"}],
                ]
            },
        }

    def build_login_prompt(self) -> dict:
        return {
            "text": (
                "🔑 Mandame tu correo y contraseña de Taiga separados por un espacio "
                "(tenés 5 minutos):\n\nEj: correo@ejemplo.com contraseña"
            ),
            "reply_markup": {
                "inline_keyboard": [[{"text": "❌ Cancelar", "callback_data": "menu:root"}]]
            },
        }

    def build_projects_menu(self, names: list[str]) -> dict:
        text = "\n".join(f"📁 {name}" for name in names) if names else "🗂️ No estás en ningún proyecto"
        return {"text": text, "reply_markup": {"inline_keyboard": [[BACK_BUTTON]]}}

    def build_pendings_menu(self, subjects: list[str]) -> dict:
        text = (
            "\n".join(f"📌 {subject}" for subject in subjects)
            if subjects
            else "📌 No tenés historias de usuario pendientes"
        )
        return {"text": text, "reply_markup": {"inline_keyboard": [[BACK_BUTTON]]}}

    def build_help_menu(self, commands: list[tuple[str, str]]) -> dict:
        lines = [f"▪️ /{name} - {description}" for name, description in commands]
        text = "🤖 Comandos disponibles:\n\n" + "\n".join(lines)
        return {"text": text, "reply_markup": {"inline_keyboard": [[BACK_BUTTON]]}}


@lru_cache
def get_menu_content() -> MenuContentService:
    return MenuContentService()
