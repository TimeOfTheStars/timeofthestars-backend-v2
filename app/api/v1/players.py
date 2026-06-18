from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_staff
from app.schemas.common import Page
from app.schemas.game import GameRead
from app.schemas.player import PlayerCreate, PlayerRead, PlayerUpdate
from app.schemas.stats import PlayerStatsBreakdown
from app.services import game_service, player_service, stats_service

router = APIRouter(prefix="/players", tags=["Players"])


@router.get("", response_model=Page[PlayerRead])
async def list_players(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    items, total = await player_service.list_players(db, page=page, size=size, search=search)
    return Page(items=items, total=total, page=page, size=size)


@router.get("/{player_id}", response_model=PlayerRead)
async def get_player(player_id: int, db: AsyncSession = Depends(get_session)):
    player = await player_service.get(db, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Игрок не найден")
    return player


@router.get("/{player_id}/stats", response_model=PlayerStatsBreakdown)
async def player_stats(
    player_id: int,
    competition_id: int | None = None,
    team_id: int | None = None,
    db: AsyncSession = Depends(get_session),
):
    player = await player_service.get(db, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Игрок не найден")
    return await stats_service.player_breakdown(
        db, player_id, competition_id=competition_id, team_id=team_id
    )


@router.get("/{player_id}/games", response_model=list[GameRead])
async def player_games(player_id: int, db: AsyncSession = Depends(get_session)):
    return await game_service.games_for_player(db, player_id)


@router.post("", response_model=PlayerRead, status_code=status.HTTP_201_CREATED)
async def create_player(
    payload: PlayerCreate, db: AsyncSession = Depends(get_session), _=Depends(require_staff)
):
    return await player_service.create(db, payload)


@router.put("/{player_id}", response_model=PlayerRead)
async def update_player(
    player_id: int,
    payload: PlayerUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_staff),
):
    player = await player_service.get(db, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Игрок не найден")
    return await player_service.update(db, player, payload)


@router.delete("/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_player(
    player_id: int, db: AsyncSession = Depends(get_session), _=Depends(require_staff)
):
    player = await player_service.get(db, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Игрок не найден")
    await player_service.delete(db, player)
