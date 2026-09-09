from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.models.enums import UserRole
from app.services.clock import format_clock

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# Шаблоны не должны сами форматировать секунды: {{ ev.time_seconds | clock }}
templates.env.filters["clock"] = format_clock


def current_admin(request: Request) -> dict | None:
    """Данные авторизованного пользователя из сессии (или None)."""
    uid = request.session.get("admin_user_id")
    if uid is None:
        return None
    return {
        "id": uid,
        "username": request.session.get("admin_username"),
        "role": request.session.get("admin_role"),
    }


def is_admin(request: Request) -> bool:
    return request.session.get("admin_role") == UserRole.admin.value


FLASH_KEY = "admin_flash"


def flash(request: Request, message: str) -> None:
    """Сообщение на следующую страницу — переживает redirect после POST."""
    request.session[FLASH_KEY] = message


def render(request: Request, template: str, **ctx):
    """Рендер с общими переменными контекста."""
    ctx.setdefault("user", current_admin(request))
    ctx.setdefault("is_admin", is_admin(request))
    # flash показывается один раз: забираем и стираем
    ctx.setdefault("flash", request.session.pop(FLASH_KEY, None))
    return templates.TemplateResponse(request, template, ctx)
