"""Блоки главной: порядок, ограничение в три штуки и совместимость со старым фронтом."""
import datetime as dt


async def _competitions(client, auth, count=4):
    out = []
    for i in range(count):
        r = await client.post(
            "/api/v1/competitions",
            json={
                "type": "tournament",
                "name": f"Кубок {i + 1}",
                "start_date": str(dt.date(2026, 3, 1)),
            },
            headers=auth,
        )
        assert r.status_code == 201, r.text
        out.append(r.json())
    return out


async def test_blocks_keep_order_and_fill_legacy_fields(client, auth):
    comps = await _competitions(client, auth)
    r = await client.put(
        "/api/v1/homepage",
        json={
            "blocks": [
                {"type": "bracket", "competition_id": comps[0]["id"], "title": "Плей-офф"},
                {"type": "standings", "competition_id": comps[1]["id"]},
                {"type": "standings", "competition_id": comps[2]["id"], "title": "Дебют"},
            ]
        },
        headers=auth,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert [b["position"] for b in body["blocks"]] == [1, 2, 3]
    assert [b["type"] for b in body["blocks"]] == ["bracket", "standings", "standings"]
    assert body["blocks"][0]["title"] == "Плей-офф"
    assert body["blocks"][1]["title"] is None
    # название соревнования приезжает вместе с блоком — без второго запроса
    assert body["blocks"][0]["competition"]["name"] == comps[0]["name"]

    # старые поля выводятся из блоков: первый блок каждого типа
    assert body["show_bracket"] is True
    assert body["bracket_competition_id"] == comps[0]["id"]
    assert body["show_standings"] is True
    assert body["standings_competition_id"] == comps[1]["id"]

    fresh = (await client.get("/api/v1/homepage")).json()
    assert fresh == body


async def test_more_than_three_blocks_rejected(client, auth):
    comps = await _competitions(client, auth)
    r = await client.put(
        "/api/v1/homepage",
        json={"blocks": [{"type": "standings", "competition_id": c["id"]} for c in comps]},
        headers=auth,
    )
    assert r.status_code == 422, r.text


async def test_unknown_competition_rejected(client, auth):
    r = await client.put(
        "/api/v1/homepage",
        json={"blocks": [{"type": "standings", "competition_id": 4242}]},
        headers=auth,
    )
    assert r.status_code == 400, r.text
    assert "4242" in r.json()["detail"]


async def test_legacy_payload_still_works(client, auth):
    comps = await _competitions(client, auth, count=2)
    r = await client.put(
        "/api/v1/homepage",
        json={
            "show_standings": True,
            "standings_competition_id": comps[0]["id"],
            "show_bracket": True,
            "bracket_competition_id": comps[1]["id"],
        },
        headers=auth,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # прежний вид настроек превращается в два блока: сначала таблица, потом сетка
    assert [(b["type"], b["competition_id"]) for b in body["blocks"]] == [
        ("standings", comps[0]["id"]),
        ("bracket", comps[1]["id"]),
    ]
    assert body["show_standings"] and body["show_bracket"]


async def test_empty_list_clears_homepage(client, auth):
    comps = await _competitions(client, auth, count=1)
    await client.put(
        "/api/v1/homepage",
        json={"blocks": [{"type": "standings", "competition_id": comps[0]["id"]}]},
        headers=auth,
    )
    r = await client.put("/api/v1/homepage", json={"blocks": []}, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["blocks"] == []
    assert r.json()["show_standings"] is False


async def test_deleting_competition_removes_its_block(client, auth):
    comps = await _competitions(client, auth, count=2)
    await client.put(
        "/api/v1/homepage",
        json={
            "blocks": [
                {"type": "standings", "competition_id": comps[0]["id"]},
                {"type": "bracket", "competition_id": comps[1]["id"]},
            ]
        },
        headers=auth,
    )
    r = await client.delete(f"/api/v1/competitions/{comps[0]['id']}", headers=auth)
    assert r.status_code == 204, r.text
    body = (await client.get("/api/v1/homepage")).json()
    assert [b["competition_id"] for b in body["blocks"]] == [comps[1]["id"]]


async def test_write_requires_auth(client, auth):
    assert (await client.get("/api/v1/homepage")).status_code == 200
    r = await client.put("/api/v1/homepage", json={"blocks": []})
    assert r.status_code == 401
