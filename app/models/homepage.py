from sqlalchemy import Boolean, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class HomepageSettings(Base, TimestampMixin):
    """Синглтон (id=1): что показывать на главном экране фронта."""

    __tablename__ = "homepage_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    show_bracket: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bracket_competition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.id", ondelete="SET NULL"), nullable=True
    )

    show_standings: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    standings_competition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.id", ondelete="SET NULL"), nullable=True
    )

    bracket_competition = relationship("Competition", foreign_keys=[bracket_competition_id])
    standings_competition = relationship("Competition", foreign_keys=[standings_competition_id])
