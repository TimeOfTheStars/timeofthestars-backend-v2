from pydantic import BaseModel, ConfigDict

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole


class UserCreate(BaseModel):
    username: str
    password: str
    role: UserRole = UserRole.manager
    is_active: bool = True


class UserUpdate(BaseModel):
    password: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: UserRole
    is_active: bool
