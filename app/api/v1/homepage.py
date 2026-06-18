from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_staff
from app.schemas.homepage import HomepageRead, HomepageUpdate
from app.services import homepage_service

router = APIRouter(prefix="/homepage", tags=["Homepage"])


@router.get("", response_model=HomepageRead)
async def get_homepage(db: AsyncSession = Depends(get_session)):
    return await homepage_service.get_settings(db)


@router.put("", response_model=HomepageRead)
async def update_homepage(
    payload: HomepageUpdate, db: AsyncSession = Depends(get_session), _=Depends(require_staff)
):
    return await homepage_service.update_settings(db, payload)
