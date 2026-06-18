from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_staff
from app.schemas.game import (
    GameCreate,
    GameRead,
    GameUpdate,
    GameWithProtocol,
    ProtocolRequest,
)
from app.schemas.game import PlayerStatLineRead
from app.schemas.player import PlayerRead
from app.services import competition_service, game_service
from app.services.competition_service import ValidationError

router = APIRouter(prefix="/games", tags=["Games"])


async def _get_or_404(db: AsyncSession, game_id: int):
    game = await game_service.get(db, game_id)
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Матч не найден")
    return game


@router.get("", response_model=list[GameRead])
async def list_games(
    competition_id: int | None = None,
    team_id: int | None = None,
    db: AsyncSession = Depends(get_session),
):
    return await game_service.list_games(db, competition_id=competition_id, team_id=team_id)


@router.get("/{game_id}", response_model=GameWithProtocol)
async def get_game(game_id: int, db: AsyncSession = Depends(get_session)):
    game = await game_service.get_with_protocol(db, game_id)
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Матч не найден")
    result = GameWithProtocol.model_validate(game, from_attributes=True)
    result.player_stats = [
        PlayerStatLineRead(
            player_id=ps.player_id,
            team_id=ps.team_id,
            goals=ps.goals,
            assists=ps.assists,
            penalties=ps.penalties,
            is_goalie=ps.is_goalie,
            goals_against=ps.goals_against,
            saves=ps.saves,
            minutes_played=ps.minutes_played,
            player=PlayerRead.model_validate(ps.player) if ps.player else None,
        )
        for ps in game.player_stats
    ]
    return result


@router.post("", response_model=GameRead, status_code=status.HTTP_201_CREATED)
async def create_game(
    payload: GameCreate, db: AsyncSession = Depends(get_session), _=Depends(require_staff)
):
    if await competition_service.get(db, payload.competition_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Соревнование не найдено")
    return await game_service.create(db, payload)


@router.put("/{game_id}", response_model=GameRead)
async def update_game(
    game_id: int,
    payload: GameUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_staff),
):
    game = await _get_or_404(db, game_id)
    return await game_service.update(db, game, payload)


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(
    game_id: int, db: AsyncSession = Depends(get_session), _=Depends(require_staff)
):
    game = await _get_or_404(db, game_id)
    await game_service.delete(db, game)


@router.put("/{game_id}/protocol", response_model=GameWithProtocol)
async def save_protocol(
    game_id: int,
    payload: ProtocolRequest,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_staff),
):
    game = await _get_or_404(db, game_id)
    try:
        await game_service.save_protocol(db, game, payload)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await get_game(game_id, db)
