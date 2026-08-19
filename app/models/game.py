from datetime import date, time

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Time, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import GameEventType, GameStage, GameStatus


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
    # Таймлайн матча. Порядок задан прямо в связи, чтобы он был одинаковым
    # и в API, и в админке.
    events: Mapped[list["GameEvent"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        order_by="(GameEvent.time_seconds, GameEvent.sort_order, GameEvent.id)",
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


PERIOD_SECONDS = 20 * 60          # длина периода
REGULATION_SECONDS = 3 * PERIOD_SECONDS   # 3600 — конец третьего периода
MAX_EVENT_SECONDS = 2 * REGULATION_SECONDS  # верхняя граница ввода времени


def period_from_seconds(seconds: int) -> int:
    """Номер периода по игровому времени.

    Границы относим к завершившемуся периоду: 1200 -> 1, 1201 -> 2, 3600 -> 3.
    Всё, что за основным временем, считаем одним овертаймом (4), а не делим
    дальше по двадцатиминуткам.
    """
    if seconds > REGULATION_SECONDS:
        return 4
    if seconds <= 0:
        return 1
    return (seconds - 1) // PERIOD_SECONDS + 1


class GameEvent(Base, TimestampMixin):
    """Событие матча: гол, удаление или смена вратаря.

    Время сквозное от начала матча, как в бумажном протоколе. Период и конец
    удаления не храним — они выводятся из времени (см. свойства ниже).
    """

    __tablename__ = "game_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[GameEventType] = mapped_column(
        Enum(GameEventType, native_enum=False, length=20), nullable=False
    )
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)

    time_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    # Разводит события с одинаковым временем (в протоколах такое бывает)
    # Ставит сервер по порядку присланного массива — клиент им не управляет
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )

    # Гол — автор; удаление — оштрафованный; смена вратаря — кто вышел на лёд
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    # SET NULL: удаление ассистента не должно уносить сам гол
    assist1_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    assist2_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )

    # Момент в видео матча (games.video_url), секунды от начала записи
    video_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Только у удалений
    penalty_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    game: Mapped["Game"] = relationship(back_populates="events")
    team = relationship("Team")
    player = relationship("Player", foreign_keys=[player_id])
    assist1 = relationship("Player", foreign_keys=[assist1_player_id])
    assist2 = relationship("Player", foreign_keys=[assist2_player_id])

    @property
    def is_goal(self) -> bool:
        return self.type in (GameEventType.goal, GameEventType.shootout_goal)

    @property
    def period(self) -> int | None:
        """Период события. У победного буллита периода нет — он вне игрового времени."""
        if self.type is GameEventType.shootout_goal:
            return None
        return period_from_seconds(self.time_seconds)

    @property
    def penalty_end_seconds(self) -> int | None:
        """Конец удаления = начало + минуты. Отдельной колонкой не храним."""
        if self.penalty_minutes is None:
            return None
        return self.time_seconds + self.penalty_minutes * 60

    def __repr__(self) -> str:
        return f"GameEvent(id={self.id}, {self.type} @ {self.time_seconds}s)"
