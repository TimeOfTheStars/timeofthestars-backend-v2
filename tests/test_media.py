from io import BytesIO

import pytest

from PIL import Image


def _png_bytes(w: int, h: int) -> bytes:
    img = Image.new("RGB", (w, h))
    # шумовой градиент, чтобы файл не сжимался в ноль и был реалистичным
    px = img.load()
    for y in range(h):
        for x in range(0, w, 7):
            px[x, y] = ((x * 3) % 256, (y * 5) % 256, (x * y) % 256)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def test_upload_compresses_to_webp_and_shrinks(client, auth):
    raw = _png_bytes(2000, 1500)  # крупное изображение
    files = {"file": ("big.png", raw, "image/png")}
    r = await client.post(
        "/api/v1/media", files=files, data={"kind": "player_photo"}, headers=auth
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # перекодировано в webp
    assert body["url"].endswith(".webp")
    assert body["content_type"] == "image/webp"
    # размер уменьшился и картинка ужата по большей стороне (player_photo → 700px)
    assert body["size"] < len(raw)
    # файл доступен по /media и реально маленькая сторона <= 700
    img_resp = await client.get(body["url"])
    assert img_resp.status_code == 200
    from PIL import Image as I

    out = I.open(BytesIO(img_resp.content))
    assert max(out.size) <= 700


async def test_upload_requires_auth(client):
    files = {"file": ("x.png", _png_bytes(10, 10), "image/png")}
    r = await client.post("/api/v1/media", files=files, data={"kind": "other"})
    assert r.status_code == 401


async def test_size_limit_fits_camera_photo(client, auth):
    """Снимок с зеркалки (10-15 МБ) не должен отсекаться по размеру.

    Проверяем именно границу: 12 МБ проходят проверку размера и падают уже
    на разборе картинки, а 26 МБ отклоняются как слишком большие.
    """
    import os

    from app.core.config import settings
    from app.db.session import async_session_maker
    from app.models.enums import MediaKind
    from app.services import media_service

    assert settings.MAX_UPLOAD_MB >= 25, "лимит меньше типового кадра с камеры"

    async with async_session_maker() as db:
        with pytest.raises(media_service.MediaError) as big:
            await media_service.save_upload(
                db, content=os.urandom(26 * 1024 * 1024),
                content_type="image/jpeg", kind=MediaKind.player_photo)
        assert "больше" in str(big.value)

        with pytest.raises(media_service.MediaError) as camera:
            await media_service.save_upload(
                db, content=os.urandom(12 * 1024 * 1024),
                content_type="image/jpeg", kind=MediaKind.player_photo)
        # дошло до разбора картинки, а не отсеклось по размеру
        assert "больше" not in str(camera.value)
