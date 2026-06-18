from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_staff
from app.models.enums import MediaKind
from app.schemas.media import MediaRead
from app.services import media_service
from app.services.media_service import MediaError, file_url

router = APIRouter(prefix="/media", tags=["Media"])


@router.post("", response_model=MediaRead, status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),
    kind: MediaKind = Form(MediaKind.other),
    db: AsyncSession = Depends(get_session),
    _=Depends(require_staff),
):
    content = await file.read()
    try:
        record = await media_service.save_upload(
            db,
            content=content,
            content_type=file.content_type,
            kind=kind,
            original_name=file.filename,
        )
    except MediaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MediaRead(
        id=record.id,
        filename=record.filename,
        content_type=record.content_type,
        size=record.size,
        kind=record.kind,
        url=file_url(record.filename),
    )
