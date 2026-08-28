from datetime import date

from pydantic import BaseModel, ConfigDict

from app.models.enums import CompetitionType
from app.schemas.player import PlayerRead
from app.schemas.team import TeamRead


class CompetitionCreate(BaseModel):
    type: CompetitionType
    name: str
    start_date: date
    end_date: date | None = None
    location: str | None = None
    logo_url: str | None = None
    show_playoff_bracket: bool = False
    show_best_players: bool = False


class CompetitionUpdate(BaseModel):
    type: CompetitionType | None = None
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    location: str | None = None
    logo_url: str | None = None
    show_playoff_bracket: bool | None = None
    show_best_players: bool | None = None
    winner_team_id: int | None = None


class CompetitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: CompetitionType
    name: str
    start_date: date
    end_date: date | None = None
    location: str | None = None
    logo_url: str | None = None
    show_playoff_bracket: bool
    show_best_players: bool
    winner_team_id: int | None = None


class CompetitionBrief(BaseModel):
    """Короткая карточка соревнования — чтобы фронт не ходил за названием отдельно."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: CompetitionType
    name: str
    logo_url: str | None = None


class AddTeamRequest(BaseModel):
    team_id: int


class AddPlayerRequest(BaseModel):
    team_id: int
    player_id: int
    number: int | None = None
    contract: bool = False


class UpdateRosterPlayerRequest(BaseModel):
    """Обновление заявки игрока: номер и/или контракт. Поля, которые не переданы,
    не меняются; `number: null` снимает номер."""

    team_id: int
    number: int | None = None
    contract: bool | None = None


class CompetitionRosterPlayer(BaseModel):
    """Игрок в составе соревнования (заявка) + информация об игроке."""

    player: PlayerRead
    team_id: int
    number: int | None = None
    contract: bool = False


class CompetitionRosterTeam(BaseModel):
    team: TeamRead
    players: list[CompetitionRosterPlayer] = []


class CompetitionPlayerWithStats(BaseModel):
    """Игрок соревнования: заявка + агрегированная статистика в этом соревновании."""

    player: PlayerRead
    team_id: int
    number: int | None = None
    contract: bool = False
    goals: int = 0
    assists: int = 0
    points: int = 0
    penalties: int = 0
    games: int = 0
