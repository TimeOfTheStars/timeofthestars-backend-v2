from sqlalchemy import Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import MediaKind


class MediaFile(Base, TimestampMixin):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[MediaKind] = mapped_column(
        Enum(MediaKind, native_enum=False, length=30), default=MediaKind.other, nullable=False
    )

    def __repr__(self) -> str:
        return f"MediaFile(id={self.id}, filename={self.filename})"
