from datetime import date, time

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import GameStage, GameStatus


class Game(Base, TimestampMixin):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    team_a_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    team_b_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)

    score_team_a: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_team_b: Mapped[int | None] = mapped_column(Integer, nullable=True)

    date: Mapped[date] = mapped_column(Date, nullable=False)
    time: Mapped[time | None] = mapped_column(Time, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    scan: Mapped[str | None] = mapped_column(String, nullable=True)
    video_url: Mapped[str | None] = mapped_column(String, nullable=True)

    stage: Mapped[GameStage] = mapped_column(
        Enum(GameStage, native_enum=False, length=20),
        default=GameStage.matches,
        nullable=False,
    )
    status: Mapped[GameStatus] = mapped_column(
        Enum(GameStatus, native_enum=False, length=20),
        default=GameStatus.scheduled,
        nullable=False,
    )

    # Победитель серии буллитов при ничьей в основное время
    bullet_win_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)

    # Структура сетки плей-офф
    round_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bracket_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_game_id: Mapped[int | None] = mapped_column(
        ForeignKey("games.id", ondelete="SET NULL"), nullable=True
    )

    team_a = relationship("Team", foreign_keys=[team_a_id])
    team_b = relationship("Team", foreign_keys=[team_b_id])
    bullet_win_team = relationship("Team", foreign_keys=[bullet_win_team_id])
    competition = relationship("Competition")

    player_stats: Mapped[list["GamePlayerStat"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"Game(id={self.id}, {self.team_a_id} vs {self.team_b_id})"


class GamePlayerStat(Base, TimestampMixin):
    """Протокол матча: статистика конкретного игрока в конкретной игре."""

    __tablename__ = "game_player_stats"
    __table_args__ = (
        UniqueConstraint("game_id", "player_id", name="uq_game_player"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)

    goals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assists: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    penalties: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_goalie: Mapped[bool] = mapped_column(default=False, nullable=False)
    goals_against: Mapped[int | None] = mapped_column(Integer, nullable=True)
    saves: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minutes_played: Mapped[int | None] = mapped_column(Integer, nullable=True)

    game: Mapped["Game"] = relationship(back_populates="player_stats")
    player = relationship("Player")
    team = relationship("Team")
