from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_staff
from app.schemas.common import Page
from app.schemas.team import TeamCreate, TeamRead, TeamUpdate
from app.services import team_service

router = APIRouter(prefix="/teams", tags=["Teams"])


@router.get("", response_model=Page[TeamRead])
async def list_teams(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    items, total = await team_service.list_teams(db, page=page, size=size, search=search)
    return Page(items=items, total=total, page=page, size=size)


@router.get("/{team_id}", response_model=TeamRead)
async def get_team(team_id: int, db: AsyncSession = Depends(get_session)):
    team = await team_service.get(db, team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Команда не найдена")
    return team


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate, db: AsyncSession = Depends(get_session), _=Depends(require_staff)
):
    return await team_service.create(db, payload)


@router.put("/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: int,
    payload: TeamUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_staff),
):
    team = await team_service.get(db, team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Команда не найдена")
    return await team_service.update(db, team, payload)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: int, db: AsyncSession = Depends(get_session), _=Depends(require_staff)
):
    team = await team_service.get(db, team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Команда не найдена")
    await team_service.delete(db, team)
