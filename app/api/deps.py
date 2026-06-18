import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import User
from app.models.enums import UserRole
from app.services import user_service

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=True)

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Недействительные учётные данные",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_session),
) -> User:
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except (jwt.PyJWTError, TypeError, ValueError) as exc:
        raise _credentials_exc from exc

    user = await user_service.get(db, user_id)
    if user is None or not user.is_active:
        raise _credentials_exc
    return user


def require_role(*roles: UserRole):
    """Зависимость: текущий пользователь должен иметь одну из ролей."""

    allowed = set(roles) or {UserRole.admin, UserRole.manager}

    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав"
            )
        return user

    return _dep


# Удобные алиасы
require_staff = require_role(UserRole.admin, UserRole.manager)
require_admin = require_role(UserRole.admin)

__all__ = ["get_session", "get_current_user", "require_role", "require_staff", "require_admin"]
