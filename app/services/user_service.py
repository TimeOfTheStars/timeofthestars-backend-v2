from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ahash_password, averify_password
from app.models import User
from app.schemas.auth import UserCreate, UserUpdate


async def get_by_username(db: AsyncSession, username: str) -> User | None:
    res = await db.execute(select(User).where(User.username == username))
    return res.scalar_one_or_none()


async def get(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def list_users(db: AsyncSession) -> Sequence[User]:
    res = await db.execute(select(User).order_by(User.id))
    return res.scalars().all()


async def authenticate(db: AsyncSession, username: str, password: str) -> User | None:
    user = await get_by_username(db, username)
    if user and user.is_active and await averify_password(password, user.hashed_password):
        return user
    return None


async def create(db: AsyncSession, data: UserCreate) -> User:
    user = User(
        username=data.username,
        hashed_password=await ahash_password(data.password),
        role=data.role,
        is_active=data.is_active,
    )
    db.add(user)
    await db.flush()
    return user


async def update(db: AsyncSession, user: User, data: UserUpdate) -> User:
    if data.password is not None:
        user.hashed_password = await ahash_password(data.password)
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    await db.flush()
    return user


async def delete(db: AsyncSession, user: User) -> None:
    await db.delete(user)
    await db.flush()
