from pydantic import BaseModel, ConfigDict

from app.models.enums import MediaKind


class MediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str | None = None
    size: int | None = None
    kind: MediaKind
    url: str
