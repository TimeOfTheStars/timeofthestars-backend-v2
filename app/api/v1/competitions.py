from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_staff
from app.models.enums import CompetitionType
from app.schemas.common import Page
from app.schemas.competition import (
    AddPlayerRequest,
    AddTeamRequest,
    CompetitionCreate,
    CompetitionPlayerWithStats,
    CompetitionRead,
    CompetitionRosterPlayer,
    CompetitionRosterTeam,
    CompetitionUpdate,
    UpdateRosterPlayerRequest,
)
from app.schemas.game import GameRead
from app.schemas.player import PlayerRead
from app.schemas.stats import BestPlayer, StandingRow
from app.schemas.team import TeamRead
from app.services import competition_service, game_service, stats_service
from app.services.competition_service import ValidationError

router = APIRouter(prefix="/competitions", tags=["Competitions"])


async def _get_or_404(db: AsyncSession, competition_id: int):
    comp = await competition_service.get(db, competition_id)
    if comp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Соревнование не найдено")
    return comp


@router.get("", response_model=Page[CompetitionRead])
async def list_competitions(
    type: CompetitionType | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
):
    items, total = await competition_service.list_competitions(db, type_=type, page=page, size=size)
    return Page(items=items, total=total, page=page, size=size)


@router.get("/{competition_id}", response_model=CompetitionRead)
async def get_competition(competition_id: int, db: AsyncSession = Depends(get_session)):
    return await _get_or_404(db, competition_id)


@router.post("", response_model=CompetitionRead, status_code=status.HTTP_201_CREATED)
async def create_competition(
    payload: CompetitionCreate, db: AsyncSession = Depends(get_session), _=Depends(require_staff)
):
    return await competition_service.create(db, payload)


@router.put("/{competition_id}", response_model=CompetitionRead)
async def update_competition(
    competition_id: int,
    payload: CompetitionUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_staff),
):
    comp = await _get_or_404(db, competition_id)
    try:
        return await competition_service.update(db, comp, payload)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{competition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_competition(
    competition_id: int, db: AsyncSession = Depends(get_session), _=Depends(require_staff)
):
    comp = await _get_or_404(db, competition_id)
    await competition_service.delete(db, comp)


# --- Состав: команды ---
@router.post("/{competition_id}/teams", status_code=status.HTTP_204_NO_CONTENT)
async def add_team(
    competition_id: int,
    payload: AddTeamRequest,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_staff),
):
    await _get_or_404(db, competition_id)
    await competition_service.add_team(db, competition_id, payload.team_id)


@router.delete("/{competition_id}/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team(
    competition_id: int,
    team_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_staff),
):
    if not await competition_service.remove_team(db, competition_id, team_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Команды нет в соревновании")


# --- Состав: игроки ---
@router.post("/{competition_id}/players", status_code=status.HTTP_204_NO_CONTENT)
async def add_player(
    competition_id: int,
    payload: AddPlayerRequest,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_staff),
):
    await _get_or_404(db, competition_id)
    await competition_service.add_player(
        db, competition_id, payload.team_id, payload.player_id, payload.number, payload.contract
    )


@router.patch("/{competition_id}/players/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_roster_player(
    competition_id: int,
    player_id: int,
    payload: UpdateRosterPlayerRequest,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_staff),
):
    """Сменить номер и/или статус контракта игрока в соревновании."""
    fields = payload.model_fields_set
    ok = await competition_service.update_roster_player(
        db,
        competition_id,
        payload.team_id,
        player_id,
        number=payload.number,
        contract=payload.contract,
        set_number="number" in fields,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Игрока нет в составе")


@router.delete(
    "/{competition_id}/players/{player_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_player(
    competition_id: int,
    player_id: int,
    team_id: int = Query(...),
    db: AsyncSession = Depends(get_session),
    _=Depends(require_staff),
):
    if not await competition_service.remove_player(db, competition_id, team_id, player_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Игрока нет в составе")


# --- Чтение состава и статистики ---
@router.get("/{competition_id}/teams", response_model=list[CompetitionRosterTeam])
async def get_roster(competition_id: int, db: AsyncSession = Depends(get_session)):
    await _get_or_404(db, competition_id)
    cts = await competition_service.get_roster(db, competition_id)
    players = await competition_service.get_players(db, competition_id)
    by_team: dict[int, list[CompetitionRosterPlayer]] = {}
    for cp in players:
        by_team.setdefault(cp.team_id, []).append(
            CompetitionRosterPlayer(
                player=PlayerRead.model_validate(cp.player),
                team_id=cp.team_id,
                number=cp.number,
                contract=cp.contract,
            )
        )
    return [
        CompetitionRosterTeam(
            team=TeamRead.model_validate(ct.team), players=by_team.get(ct.team_id, [])
        )
        for ct in cts
    ]


@router.get("/{competition_id}/players", response_model=list[CompetitionPlayerWithStats])
async def get_competition_players(competition_id: int, db: AsyncSession = Depends(get_session)):
    await _get_or_404(db, competition_id)
    return await stats_service.competition_players_with_stats(db, competition_id)


@router.get("/{competition_id}/standings", response_model=list[StandingRow])
async def get_standings(competition_id: int, db: AsyncSession = Depends(get_session)):
    await _get_or_404(db, competition_id)
    return await stats_service.compute_standings(db, competition_id)


@router.get("/{competition_id}/best-players", response_model=list[BestPlayer])
async def get_best_players(
    competition_id: int, limit: int = Query(10, ge=1, le=100), db: AsyncSession = Depends(get_session)
):
    await _get_or_404(db, competition_id)
    return await stats_service.best_players(db, competition_id, limit=limit)


@router.get("/{competition_id}/games", response_model=list[GameRead])
async def get_competition_games(competition_id: int, db: AsyncSession = Depends(get_session)):
    await _get_or_404(db, competition_id)
    return await game_service.list_games(db, competition_id=competition_id)
