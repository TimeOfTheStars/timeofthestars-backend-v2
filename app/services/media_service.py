import secrets
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.models import MediaFile
from app.models.enums import MediaKind

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_TYPES = ALLOWED_IMAGE_TYPES | {"application/pdf"}
EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}

# Максимальный размер (по большей стороне) и качество WebP по типу медиа.
MAX_DIM = {
    MediaKind.team_logo: 512,
    MediaKind.competition_logo: 512,
    MediaKind.player_photo: 700,
    MediaKind.game_scan: 1800,
    MediaKind.other: 1600,
}
WEBP_QUALITY = 82


class MediaError(Exception):
    pass


def media_root() -> Path:
    root = Path(settings.MEDIA_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def file_url(filename: str) -> str:
    return f"/media/{filename}"


def _compress_image(content: bytes, max_dim: int) -> bytes:
    """Сжимает картинку: коррекция ориентации, ресайз вниз, перекодирование в WebP."""
    try:
        img = Image.open(BytesIO(content))
        img = ImageOps.exif_transpose(img)  # учесть EXIF-ориентацию (фото с телефона)
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaError("Не удалось обработать изображение") from exc

    # Сохраняем прозрачность, если есть; иначе плоский RGB
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    img = img.convert("RGBA" if has_alpha else "RGB")

    # thumbnail только уменьшает (апскейла не будет)
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    out = BytesIO()
    img.save(out, format="WEBP", quality=WEBP_QUALITY, method=6)
    return out.getvalue()


async def save_upload(
    db: AsyncSession,
    *,
    content: bytes,
    content_type: str | None,
    kind: MediaKind,
    original_name: str | None = None,
) -> MediaFile:
    if content_type not in ALLOWED_TYPES:
        raise MediaError(f"Недопустимый тип файла: {content_type}")
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise MediaError(f"Файл больше {settings.MAX_UPLOAD_MB} МБ")

    if content_type in ALLOWED_IMAGE_TYPES:
        # Сжатие и перекодирование в WebP — в пуле потоков: LANCZOS + method=6
        # занимают 200-500 мс CPU и иначе блокируют весь event loop.
        content = await run_in_threadpool(_compress_image, content, MAX_DIM.get(kind, 1600))
        content_type = "image/webp"
        ext = ".webp"
    else:
        ext = EXT_BY_TYPE.get(content_type, "")

    filename = f"{secrets.token_hex(16)}{ext}"
    path = media_root() / filename
    await run_in_threadpool(path.write_bytes, content)

    record = MediaFile(
        filename=filename, content_type=content_type, size=len(content), kind=kind
    )
    db.add(record)
    await db.flush()
    return record
