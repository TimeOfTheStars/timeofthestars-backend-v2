from io import BytesIO

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
