import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GameEventType, GameStage, GameStatus
from app.models.game import MAX_EVENT_SECONDS
from app.schemas.player import PlayerRead


class GameCreate(BaseModel):
    competition_id: int
    team_a_id: int
    team_b_id: int
    date: dt.date
    time: dt.time | None = None
    location: str | None = None
    score_team_a: int | None = None
    score_team_b: int | None = None
    stage: GameStage = GameStage.matches
    status: GameStatus = GameStatus.scheduled
    bullet_win_team_id: int | None = None
    scan: str | None = None
    video_url: str | None = None
    round_no: int | None = None
    bracket_slot: int | None = None
    next_game_id: int | None = None


class GameUpdate(BaseModel):
    team_a_id: int | None = None
    team_b_id: int | None = None
    date: dt.date | None = None
    time: dt.time | None = None
    location: str | None = None
    score_team_a: int | None = None
    score_team_b: int | None = None
    stage: GameStage | None = None
    status: GameStatus | None = None
    bullet_win_team_id: int | None = None
    scan: str | None = None
    video_url: str | None = None
    round_no: int | None = None
    bracket_slot: int | None = None
    next_game_id: int | None = None


class GameRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competition_id: int
    team_a_id: int
    team_b_id: int
    score_team_a: int | None = None
    score_team_b: int | None = None
    date: dt.date
    time: dt.time | None = None
    location: str | None = None
    scan: str | None = None
    video_url: str | None = None
    stage: GameStage
    status: GameStatus
    bullet_win_team_id: int | None = None
    round_no: int | None = None
    bracket_slot: int | None = None
    next_game_id: int | None = None


class PlayerStatLine(BaseModel):
    """Строка участия игрока в матче (вход).

    Голы, передачи и штрафные минуты сюда НЕ передаются: они выводятся из
    событий матча. extra="forbid" — намеренно: если клиент всё ещё присылает
    goals/assists/penalties, лучше внятная 422, чем молчаливое обнуление цифр.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    player_id: int
    team_id: int
    is_goalie: bool = False
    goals_against: int | None = None
    saves: int | None = None
    minutes_played: int | None = None


class PlayerStatLineRead(BaseModel):
    """Строка протокола по игроку (выход). Форма для фронта не менялась."""

    model_config = ConfigDict(from_attributes=True)

    player_id: int
    team_id: int
    goals: int = 0
    assists: int = 0
    penalties: int = 0
    is_goalie: bool = False
    goals_against: int | None = None
    saves: int | None = None
    minutes_played: int | None = None
    player: PlayerRead | None = None


class GameEventIn(BaseModel):
    """Событие матча на вход. time_seconds — сквозное игровое время от начала.

    sort_order здесь нет: порядок событий внутри одной секунды сервер берёт
    из порядка присланного массива.
    """

    model_config = ConfigDict(extra="forbid")

    type: GameEventType
    team_id: int
    time_seconds: int = Field(ge=0, le=MAX_EVENT_SECONDS)
    player_id: int
    assist1_player_id: int | None = None
    assist2_player_id: int | None = None
    video_seconds: int | None = Field(default=None, ge=0)
    penalty_minutes: int | None = Field(default=None, gt=0)


class GameEventRead(BaseModel):
    """Событие матча на выход. period и penalty_end_seconds вычисляются."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: GameEventType
    team_id: int
    time_seconds: int
    period: int | None = None
    sort_order: int
    player_id: int
    assist1_player_id: int | None = None
    assist2_player_id: int | None = None
    video_seconds: int | None = None
    penalty_minutes: int | None = None
    penalty_end_seconds: int | None = None
    player: PlayerRead | None = None
    assist1: PlayerRead | None = None
    assist2: PlayerRead | None = None


class ProtocolRequest(BaseModel):
    """Полный протокол матча: счёт, участники и события (заменяет существующий).

    events=None — таймлайн не трогаем (цифры выводятся из уже сохранённых
    событий). events=[] — таймлайн очищается, производные цифры обнуляются.
    """

    model_config = ConfigDict(extra="forbid")

    score_team_a: int | None = None
    score_team_b: int | None = None
    bullet_win_team_id: int | None = None
    stat_lines: list[PlayerStatLine] = []
    events: list[GameEventIn] | None = None


class GameWithProtocol(GameRead):
    player_stats: list[PlayerStatLineRead] = []
    events: list[GameEventRead] = []
