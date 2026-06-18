import datetime as dt

from pydantic import BaseModel, ConfigDict

from app.models.enums import GameStage, GameStatus
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
    """Строка протокола по игроку (вход и выход)."""

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


class PlayerStatLineRead(PlayerStatLine):
    player: PlayerRead | None = None


class ProtocolRequest(BaseModel):
    """Полный протокол матча: счёт + статистика игроков (заменяет существующий)."""

    score_team_a: int | None = None
    score_team_b: int | None = None
    bullet_win_team_id: int | None = None
    stat_lines: list[PlayerStatLine] = []


class GameWithProtocol(GameRead):
    player_stats: list[PlayerStatLineRead] = []
