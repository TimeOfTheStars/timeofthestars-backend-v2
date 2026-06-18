from datetime import date

from pydantic import BaseModel, ConfigDict

from app.models.enums import PlayerPosition


class PlayerCreate(BaseModel):
    full_name: str
    birth_date: date | None = None
    position: PlayerPosition | None = None
    grip: str | None = None
    photo_url: str | None = None


class PlayerUpdate(BaseModel):
    full_name: str | None = None
    birth_date: date | None = None
    position: PlayerPosition | None = None
    grip: str | None = None
    photo_url: str | None = None


class PlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    birth_date: date | None = None
    position: PlayerPosition | None = None
    grip: str | None = None
    photo_url: str | None = None
