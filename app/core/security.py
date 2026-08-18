from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext
from starlette.concurrency import run_in_threadpool

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# Асинхронные обёртки: bcrypt cost 12 — это 250-400 мс CPU, из async-контекста
# его нельзя вызывать напрямую, иначе встаёт весь event loop.
# Синхронные версии остаются для create_admin.py, который работает вне event loop.
async def ahash_password(password: str) -> str:
    return await run_in_threadpool(hash_password, password)


async def averify_password(plain: str, hashed: str) -> bool:
    return await run_in_threadpool(verify_password, plain, hashed)


def create_access_token(subject: str, role: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": str(subject), "role": role, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Возвращает payload или бросает jwt.PyJWTError."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
