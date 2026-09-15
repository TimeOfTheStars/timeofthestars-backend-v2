import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GameEventType, GameStage, GameStatus
from app.models.game import MAX_EVENT_SECONDS
from app.schemas.player import PlayerRead
from app.schemas.team import TeamRead


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


class GameTeamStatIn(BaseModel):
    """Командные итоги матча на вход.

    Штрафных минут здесь нет: они выводятся из событий. Реализация — готовый
    процент, её на табло считают то от всех бросков, то от бросков в створ.
    """

    model_config = ConfigDict(extra="forbid")

    team_id: int
    shots: int | None = Field(default=None, ge=0)
    shots_on_goal: int | None = Field(default=None, ge=0)
    faceoffs_won: int | None = Field(default=None, ge=0)
    conversion_percent: int | None = Field(default=None, ge=0, le=100)


class GameTeamStatRead(BaseModel):
    """Командные итоги на выход. penalty_minutes считается из событий матча."""

    model_config = ConfigDict(from_attributes=True)

    team_id: int
    shots: int | None = None
    shots_on_goal: int | None = None
    faceoffs_won: int | None = None
    conversion_percent: int | None = None
    penalty_minutes: int = 0


class ProtocolRequest(BaseModel):
    """Полный протокол матча: счёт, участники и события (заменяет существующий).

    events=None — таймлайн не трогаем (цифры выводятся из уже сохранённых
    событий). events=[] — таймлайн очищается, производные цифры обнуляются.
    Так же и team_stats: None — не трогаем, [] — стираем командные итоги.
    """

    model_config = ConfigDict(extra="forbid")

    score_team_a: int | None = None
    score_team_b: int | None = None
    bullet_win_team_id: int | None = None
    stat_lines: list[PlayerStatLine] = []
    events: list[GameEventIn] | None = None
    team_stats: list[GameTeamStatIn] | None = None


class GameWithProtocol(GameRead):
    player_stats: list[PlayerStatLineRead] = []
    events: list[GameEventRead] = []
    team_stats: list[GameTeamStatRead] = []


class PlayerGoalMoment(BaseModel):
    """Гол игрока с таймкодом в видео матча — для карточки игрока.

    Попадают только голы самого игрока (передачи отдельными записями не идут)
    и только те, у которых есть и video_seconds, и video_url у матча — иначе
    показывать было бы нечего. Поэтому три видео-поля здесь не Optional.
    """

    event_id: int
    game_id: int
    type: GameEventType                 # goal | shootout_goal — буллит тоже гол
    period: int | None = None           # None у буллита
    time_seconds: int                   # игровое время гола, как в протоколе
    video_seconds: int
    video_url: str
    video_at_url: str                   # готовая ссылка на момент: …?t=45m5s

    date: dt.date
    competition_id: int
    competition_name: str
    # Счёт и соперник — с точки зрения команды игрока, чтобы карточка не
    # соображала сама, с какой он стороны.
    team: TeamRead
    opponent: TeamRead
    score_for: int | None = None
    score_against: int | None = None
    assist1: PlayerRead | None = None
    assist2: PlayerRead | None = None
