from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.models.enums import UserRole

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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


def render(request: Request, template: str, **ctx):
    """Рендер с общими переменными контекста."""
    ctx.setdefault("user", current_admin(request))
    ctx.setdefault("is_admin", is_admin(request))
    return templates.TemplateResponse(request, template, ctx)
