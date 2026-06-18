from pydantic import BaseModel

from app.schemas.player import PlayerRead
from app.schemas.team import TeamRead


class StandingRow(BaseModel):
    team: TeamRead
    games: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    goals_scored: int = 0
    goals_conceded: int = 0
    extra_points: int = 0  # очки за победу по буллитам
    points: int = 0


class PlayerStatTotals(BaseModel):
    games: int = 0
    goals: int = 0
    assists: int = 0
    points: int = 0          # голы + пасы
    penalties: int = 0
    # вратарские
    goals_against: int = 0
    saves: int = 0
    minutes_played: int = 0


class PlayerCompetitionStat(BaseModel):
    competition_id: int
    competition_name: str
    totals: PlayerStatTotals


class PlayerTeamStat(BaseModel):
    team_id: int
    team_name: str
    totals: PlayerStatTotals


class PlayerStatsBreakdown(BaseModel):
    player_id: int
    career: PlayerStatTotals
    by_competition: list[PlayerCompetitionStat] = []
    by_team: list[PlayerTeamStat] = []


class BestPlayer(BaseModel):
    player: PlayerRead
    team_id: int | None = None
    goals: int = 0
    assists: int = 0
    points: int = 0
    penalties: int = 0
