import datetime as dt


async def _login(client):
    r = await client.post(
        "/admin/login", data={"username": "admin", "password": "admin"}, follow_redirects=False
    )
    assert r.status_code == 303, r.text


async def test_admin_login_page(client):
    r = await client.get("/admin/login")
    assert r.status_code == 200
    assert "Войти" in r.text


async def test_admin_requires_login(client):
    r = await client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/login"


async def test_admin_dashboard_and_pages(client):
    await _login(client)
    paths = (
        "/admin", "/admin/teams", "/admin/teams/new",
        "/admin/players", "/admin/players/new",
        "/admin/competitions", "/admin/competitions/new",
        "/admin/homepage", "/admin/users",
    )
    for path in paths:
        r = await client.get(path)
        assert r.status_code == 200, f"{path}: {r.status_code}"


async def test_dashboard_shows_games_this_week(client, auth):
    # команды и соревнование через API
    import datetime as _dt

    a = (await client.post("/api/v1/teams", json={"name": "Альфа"}, headers=auth)).json()
    b = (await client.post("/api/v1/teams", json={"name": "Бета"}, headers=auth)).json()
    comp = (await client.post(
        "/api/v1/competitions",
        json={"type": "championship", "name": "Неделя", "start_date": str(_dt.date(2026, 1, 1))},
        headers=auth,
    )).json()
    await client.post(
        "/api/v1/games",
        json={
            "competition_id": comp["id"], "team_a_id": a["id"], "team_b_id": b["id"],
            "date": str(_dt.date.today()),
        },
        headers=auth,
    )
    await _login(client)
    r = await client.get("/admin")
    assert r.status_code == 200
    assert "Игры на этой неделе" in r.text
    assert "сегодня" in r.text
    assert "Альфа" in r.text and "Бета" in r.text


async def test_players_pagination(client, auth):
    for i in range(12):
        await client.post("/api/v1/players", json={"full_name": f"Игрок {i:02d}"}, headers=auth)
    await _login(client)
    r = await client.get("/admin/players?size=10")
    assert r.status_code == 200
    assert "Стр. 1 из 2" in r.text
    assert "size=10&amp;page=2" in r.text or "size=10&page=2" in r.text
    # вторая страница доступна
    r2 = await client.get("/admin/players?size=10&page=2")
    assert r2.status_code == 200
    # селектор размеров присутствует
    assert "Показывать по" in r.text


async def test_bulk_add_teams_modal(client, auth):
    import datetime as _dt

    ids = []
    for n in ("К1", "К2", "К3"):
        ids.append((await client.post("/api/v1/teams", json={"name": n}, headers=auth)).json()["id"])
    comp = (await client.post(
        "/api/v1/competitions",
        json={"type": "championship", "name": "Опт", "start_date": str(_dt.date(2026, 1, 1))},
        headers=auth,
    )).json()
    await _login(client)
    # на странице есть кнопка и модалка
    page = await client.get(f"/admin/competitions/{comp['id']}")
    assert "Добавить несколько" in page.text
    assert 'id="m-add-teams"' in page.text
    # массово добавляем 2 из 3 команд
    r = await client.post(
        f"/admin/competitions/{comp['id']}/teams/bulk",
        data={"team_ids": [str(ids[0]), str(ids[2])]},
        follow_redirects=False,
    )
    assert r.status_code == 303
    standings = (await client.get(f"/api/v1/competitions/{comp['id']}/standings")).json()
    names = {row["team"]["name"] for row in standings}
    assert names == {"К1", "К3"}


async def test_bulk_add_players_modal(client, auth):
    import datetime as _dt

    team = (await client.post("/api/v1/teams", json={"name": "Сборная"}, headers=auth)).json()
    pids = []
    for n in ("Игрок 1", "Игрок 2", "Игрок 3"):
        pids.append((await client.post("/api/v1/players", json={"full_name": n}, headers=auth)).json()["id"])
    comp = (await client.post(
        "/api/v1/competitions",
        json={"type": "championship", "name": "ОптИгр", "start_date": str(_dt.date(2026, 1, 1))},
        headers=auth,
    )).json()
    await client.post(f"/api/v1/competitions/{comp['id']}/teams", json={"team_id": team["id"]}, headers=auth)

    await _login(client)
    page = await client.get(f"/admin/competitions/{comp['id']}")
    assert f"m-add-players-{team['id']}" in page.text

    r = await client.post(
        f"/admin/competitions/{comp['id']}/players/bulk",
        data={"team_id": str(team["id"]), "player_ids": [str(pids[0]), str(pids[2])]},
        follow_redirects=False,
    )
    assert r.status_code == 303
    players = (await client.get(f"/api/v1/competitions/{comp['id']}/players")).json()
    got = {p["player"]["full_name"] for p in players}
    assert got == {"Игрок 1", "Игрок 3"}


async def test_admin_create_competition_and_protocol_flow(client):
    await _login(client)
    # команды и игроки через админ-формы
    await client.post("/admin/teams", data={"name": "Сокол", "city": "Москва"}, follow_redirects=True)
    await client.post("/admin/teams", data={"name": "Молния", "city": "Тула"}, follow_redirects=True)
    await client.post(
        "/admin/players", data={"full_name": "Иван Петров", "position": "нападающий"}, follow_redirects=True
    )

    # соревнование
    r = await client.post(
        "/admin/competitions",
        data={"name": "Кубок", "type": "championship", "start_date": str(dt.date(2026, 1, 1))},
        follow_redirects=False,
    )
    assert r.status_code == 303
    comp_url = r.headers["location"]
    page = await client.get(comp_url)
    assert page.status_code == 200
    assert "Кубок" in page.text

    # добавить обе команды и создать матч, открыть протокол
    cid = comp_url.rsplit("/", 1)[-1]
    teams = (await client.get("/api/v1/teams")).json()["items"]
    for t in teams:
        await client.post(f"/admin/competitions/{cid}/teams", data={"team_id": t["id"]}, follow_redirects=True)
    await client.post(
        f"/admin/competitions/{cid}/games",
        data={
            "team_a_id": teams[0]["id"], "team_b_id": teams[1]["id"],
            "date": str(dt.date(2026, 1, 5)), "stage": "matches",
        },
        follow_redirects=True,
    )
    games = (await client.get(f"/api/v1/competitions/{cid}/games")).json()
    assert games, "матч не создан"
    r = await client.get(f"/admin/games/{games[0]['id']}/protocol")
    assert r.status_code == 200
    assert "Сохранить протокол" in r.text

    # экран редактирования матча
    gid = games[0]["id"]
    r = await client.get(f"/admin/games/{gid}/edit")
    assert r.status_code == 200
    assert "Редактирование матча" in r.text
    r = await client.post(
        f"/admin/games/{gid}/edit",
        data={
            "team_a_id": teams[1]["id"], "team_b_id": teams[0]["id"],
            "date": str(dt.date(2026, 2, 9)), "time": "20:30", "stage": "final",
            "location": "Дворец спорта",
            "video_url": "https://vkvideo.ru/abc",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    g = (await client.get(f"/api/v1/games/{gid}")).json()
    assert g["date"] == "2026-02-09"
    assert g["stage"] == "final"
    assert g["team_a_id"] == teams[1]["id"]
    assert g["location"] == "Дворец спорта"
    assert g["video_url"] == "https://vkvideo.ru/abc"
