from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_staff
from app.schemas.homepage import HomepageBlockRead, HomepageRead, HomepageUpdate
from app.services import homepage_service
from app.services.competition_service import ValidationError

router = APIRouter(prefix="/homepage", tags=["Homepage"])


def _view(blocks) -> HomepageRead:
    return HomepageRead(
        blocks=[HomepageBlockRead.model_validate(b, from_attributes=True) for b in blocks],
        **homepage_service.legacy_view(blocks),
    )


@router.get("", response_model=HomepageRead)
async def get_homepage(db: AsyncSession = Depends(get_session)):
    return _view(await homepage_service.get_blocks(db))


@router.put("", response_model=HomepageRead)
async def update_homepage(
    payload: HomepageUpdate, db: AsyncSession = Depends(get_session), _=Depends(require_staff)
):
    try:
        blocks = await homepage_service.update_settings(db, payload)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _view(blocks)
