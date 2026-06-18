from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import CompetitionType


class Competition(Base, TimestampMixin):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[CompetitionType] = mapped_column(
        Enum(CompetitionType, native_enum=False, length=20), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String, nullable=True)

    # Флаги отображения на фронте
    show_playoff_bracket: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    show_best_players: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Победитель (из команд-участниц; ограничение проверяется в сервисе)
    winner_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )

    teams: Mapped[list["CompetitionTeam"]] = relationship(
        back_populates="competition", cascade="all, delete-orphan"
    )
    players: Mapped[list["CompetitionPlayer"]] = relationship(
        back_populates="competition", cascade="all, delete-orphan"
    )
    winner_team = relationship("Team", foreign_keys=[winner_team_id])

    def __repr__(self) -> str:
        return f"Competition(id={self.id}, name={self.name}, type={self.type})"


class CompetitionTeam(Base, TimestampMixin):
    """Команда-участница соревнования. Статистику не храним — считаем на лету."""

    __tablename__ = "competition_teams"
    __table_args__ = (
        UniqueConstraint("competition_id", "team_id", name="uq_competition_team"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)

    competition: Mapped["Competition"] = relationship(back_populates="teams")
    team = relationship("Team")


class CompetitionPlayer(Base, TimestampMixin):
    """Заявка игрока за команду в соревновании. Личную статистику не храним."""

    __tablename__ = "competition_players"
    __table_args__ = (
        UniqueConstraint(
            "competition_id", "team_id", "player_id", name="uq_competition_team_player"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    competition: Mapped["Competition"] = relationship(back_populates="players")
    team = relationship("Team")
    player = relationship("Player")
