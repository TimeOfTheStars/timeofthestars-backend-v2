from datetime import date

from sqlalchemy import Date, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import PlayerPosition


class Player(Base, TimestampMixin):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    position: Mapped[PlayerPosition | None] = mapped_column(
        Enum(
            PlayerPosition,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )
    grip: Mapped[str | None] = mapped_column(String, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        return f"Player(id={self.id}, full_name={self.full_name})"
