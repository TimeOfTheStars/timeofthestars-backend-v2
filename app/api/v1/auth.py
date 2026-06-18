from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, require_admin
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import TokenResponse, UserCreate, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_session),
):
    user = await user_service.authenticate(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль"
        )
    token = create_access_token(subject=user.id, role=user.role)
    return TokenResponse(access_token=token, role=user.role)


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user)):
    return user


# --- Управление пользователями (только admin) ---
users_router = APIRouter(prefix="/users", tags=["Users"])


@users_router.get("", response_model=list[UserRead])
async def list_users(db: AsyncSession = Depends(get_session), _: User = Depends(require_admin)):
    return await user_service.list_users(db)


@users_router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_admin),
):
    if await user_service.get_by_username(db, payload.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Логин занят")
    return await user_service.create(db, payload)


@users_router.put("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_admin),
):
    user = await user_service.get(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    return await user_service.update(db, user, payload)


@users_router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_admin),
):
    user = await user_service.get(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    await user_service.delete(db, user)


router.include_router(users_router)
