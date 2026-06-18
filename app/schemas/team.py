from pydantic import BaseModel, ConfigDict


class TeamBase(BaseModel):
    name: str
    slug: str | None = None
    city: str | None = None
    logo_url: str | None = None


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    city: str | None = None
    logo_url: str | None = None


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    city: str | None = None
    logo_url: str | None = None
