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
    # на экране появился таймлайн с шаблоном строки события
    assert "Хронология" in r.text
    assert 'id="ev-tpl"' in r.text
    assert 'id="roster-data"' in r.text

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


async def test_admin_protocol_form_roundtrip(client):
    """Ввод протокола через форму админки: события парсятся, цифры выводятся."""
    await client.post("/admin/login", data={"username": "admin", "password": "admin"})
    for name in ("Вихрь", "Гроза"):
        await client.post("/admin/teams", data={"name": name, "city": "Тверь"}, follow_redirects=True)
    teams = (await client.get("/api/v1/teams")).json()["items"]
    for full_name, position in (("Первый Бомбардир", "нападающий"), ("Второй Пасующий", "защитник")):
        await client.post(
            "/admin/players", data={"full_name": full_name, "position": position}, follow_redirects=True
        )
    players = (await client.get("/api/v1/players")).json()["items"]
    await client.post(
        "/admin/competitions",
        data={"type": "tournament", "name": "Форма-кубок", "start_date": "2026-04-01"},
        follow_redirects=True,
    )
    cid = (await client.get("/api/v1/competitions")).json()["items"][0]["id"]
    for t in teams[:2]:
        await client.post(
            f"/admin/competitions/{cid}/teams", data={"team_id": t["id"]}, follow_redirects=True
        )
    for pl in players[:2]:
        await client.post(
            f"/admin/competitions/{cid}/players",
            data={"team_id": teams[0]["id"], "player_id": pl["id"], "number": 7},
            follow_redirects=True,
        )
    await client.post(
        f"/admin/competitions/{cid}/games",
        data={
            "team_a_id": teams[0]["id"], "team_b_id": teams[1]["id"],
            "date": "2026-04-05", "stage": "matches",
        },
        follow_redirects=True,
    )
    gid = (await client.get(f"/api/v1/competitions/{cid}/games")).json()[0]["id"]
    scorer, helper = players[0]["id"], players[1]["id"]

    form = {
        "score_team_a": "1",
        "score_team_b": "0",
        "bullet_win_team_id": "",
        f"pid-{scorer}-{teams[0]['id']}": "on",
        f"pid-{helper}-{teams[0]['id']}": "on",
        # время в человеческом виде — сервер сам переведёт в секунды
        "ev-0-time": "16:00",
        "ev-0-type": "goal",
        "ev-0-team_id": str(teams[0]["id"]),
        "ev-0-player_id": str(scorer),
        "ev-0-assist1_player_id": str(helper),
        "ev-0-video_time": "45:05",
        # пустая заготовка строки должна молча выброситься
        "ev-5-time": "",
        "ev-5-type": "goal",
        "ev-5-team_id": str(teams[0]["id"]),
        "ev-5-player_id": "",
        # дыра в нумерации не мешает
        "ev-9-time": "41:45",
        "ev-9-type": "penalty",
        "ev-9-team_id": str(teams[0]["id"]),
        "ev-9-player_id": str(helper),
        "ev-9-penalty_minutes": "2",
    }
    r = await client.post(f"/admin/games/{gid}/protocol", data=form, follow_redirects=False)
    assert r.status_code == 303, r.text

    game = (await client.get(f"/api/v1/games/{gid}")).json()
    assert [e["time_seconds"] for e in game["events"]] == [960, 2505]
    goal = game["events"][0]
    assert goal["video_seconds"] == 2705
    assert goal["assist1_player_id"] == helper
    stats = {s["player_id"]: s for s in game["player_stats"]}
    assert stats[scorer]["goals"] == 1
    assert stats[helper]["assists"] == 1
    assert stats[helper]["penalties"] == 2

    # экран открывается заново с заполненным таймлайном, и выбор игрока
    # отрисован на сервере — форма работоспособна и без JS
    r = await client.get(f"/admin/games/{gid}/protocol")
    assert r.status_code == 200
    assert 'value="16:00"' in r.text
    assert 'value="41:45"' in r.text
    assert f'value="{scorer}" selected' in r.text


async def test_admin_protocol_bad_time_preserves_input(client):
    """Ошибка в одном поле не должна стирать набранный протокол."""
    await client.post("/admin/login", data={"username": "admin", "password": "admin"})
    for name in ("Комета", "Метель"):
        await client.post("/admin/teams", data={"name": name}, follow_redirects=True)
    teams = (await client.get("/api/v1/teams")).json()["items"]
    await client.post("/admin/players", data={"full_name": "Игрок Тестовый"}, follow_redirects=True)
    pid = (await client.get("/api/v1/players")).json()["items"][0]["id"]
    await client.post(
        "/admin/competitions",
        data={"type": "tournament", "name": "Кубок ошибок", "start_date": "2026-05-01"},
        follow_redirects=True,
    )
    cid = (await client.get("/api/v1/competitions")).json()["items"][0]["id"]
    for t in teams[:2]:
        await client.post(
            f"/admin/competitions/{cid}/teams", data={"team_id": t["id"]}, follow_redirects=True
        )
    await client.post(
        f"/admin/competitions/{cid}/players",
        data={"team_id": teams[0]["id"], "player_id": pid, "number": 11},
        follow_redirects=True,
    )
    await client.post(
        f"/admin/competitions/{cid}/games",
        data={
            "team_a_id": teams[0]["id"], "team_b_id": teams[1]["id"],
            "date": "2026-05-05", "stage": "matches",
        },
        follow_redirects=True,
    )
    gid = (await client.get(f"/api/v1/competitions/{cid}/games")).json()[0]["id"]

    r = await client.post(
        f"/admin/games/{gid}/protocol",
        data={
            "score_team_a": "1",
            "score_team_b": "0",
            f"pid-{pid}-{teams[0]['id']}": "on",
            "ev-0-time": "16;00",          # опечатка
            "ev-0-type": "goal",
            "ev-0-team_id": str(teams[0]["id"]),
            "ev-0-player_id": str(pid),
        },
        follow_redirects=False,
    )
    assert r.status_code == 200, "должна вернуться форма, а не редирект"
    assert "16;00" in r.text, "введённое значение должно вернуться в форму"
    assert "непонятно" in r.text
    # в базу ничего не записалось
    game = (await client.get(f"/api/v1/games/{gid}")).json()
    assert game["events"] == []
    assert game["player_stats"] == []
    assert game["score_team_a"] is None


def _small_png() -> bytes:
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGB", (700, 700), (30, 80, 160))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def test_admin_competition_edit_and_logo(client):
    """Соревнование можно отредактировать целиком и поставить ему логотип."""
    await client.post("/admin/login", data={"username": "admin", "password": "admin"})
    await client.post("/admin/teams", data={"name": "Ястребы"}, follow_redirects=True)
    team_id = (await client.get("/api/v1/teams")).json()["items"][0]["id"]
    await client.post(
        "/admin/competitions",
        data={"type": "tournament", "name": "Кубок черновой", "start_date": "2026-06-01"},
        follow_redirects=True,
    )
    cid = (await client.get("/api/v1/competitions")).json()["items"][0]["id"]
    await client.post(
        f"/admin/competitions/{cid}/teams", data={"team_id": team_id}, follow_redirects=True
    )

    # в списке появилась кнопка редактирования
    r = await client.get("/admin/competitions")
    assert r.status_code == 200
    assert f'href="/admin/competitions/{cid}/edit"' in r.text

    # страница редактирования открывается и показывает текущие значения
    r = await client.get(f"/admin/competitions/{cid}/edit")
    assert r.status_code == 200
    assert "Редактирование соревнования" in r.text
    assert 'value="Кубок черновой"' in r.text
    assert 'value="2026-06-01"' in r.text
    assert 'name="logo"' in r.text

    # правим всё, включая тип, даты и логотип
    r = await client.post(
        f"/admin/competitions/{cid}/edit",
        data={
            "name": "Чемпионат имени себя",
            "type": "championship",
            "start_date": "2026-09-15",
            "end_date": "2027-04-30",
            "location": "Ярославль",
            "winner_team_id": str(team_id),
            "show_best_players": "on",
        },
        files={"logo": ("logo.png", _small_png(), "image/png")},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text

    comp = (await client.get(f"/api/v1/competitions/{cid}")).json()
    assert comp["name"] == "Чемпионат имени себя"
    assert comp["type"] == "championship"
    assert comp["start_date"] == "2026-09-15"
    assert comp["end_date"] == "2027-04-30"
    assert comp["location"] == "Ярославль"
    assert comp["show_best_players"] is True
    assert comp["show_playoff_bracket"] is False
    assert comp["logo_url"] and comp["logo_url"].startswith("/media/")
    assert comp["logo_url"].endswith(".webp"), "логотип должен ужаться в webp"

    # логотип виден на детальной странице и в списке
    r = await client.get(f"/admin/competitions/{cid}")
    assert comp["logo_url"] in r.text
    assert "Изменить" in r.text
    r = await client.get("/admin/competitions")
    assert comp["logo_url"] in r.text

    # повторное сохранение без файла не должно стирать логотип
    r = await client.post(
        f"/admin/competitions/{cid}/edit",
        data={
            "name": "Чемпионат имени себя",
            "type": "championship",
            "start_date": "2026-09-15",
            "location": "Ярославль",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    again = (await client.get(f"/api/v1/competitions/{cid}")).json()
    assert again["logo_url"] == comp["logo_url"], "логотип потерялся при сохранении без файла"
    # пустая дата окончания означает «убрать»
    assert again["end_date"] is None


async def test_admin_competition_create_with_logo(client):
    """Логотип можно приложить сразу при создании."""
    await client.post("/admin/login", data={"username": "admin", "password": "admin"})
    r = await client.post(
        "/admin/competitions",
        data={"type": "tournament", "name": "Кубок с гербом", "start_date": "2026-07-01"},
        files={"logo": ("emblem.png", _small_png(), "image/png")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    comp = (await client.get("/api/v1/competitions")).json()["items"][0]
    assert comp["name"] == "Кубок с гербом"
    assert comp["logo_url"] and comp["logo_url"].endswith(".webp")


async def test_admin_homepage_blocks(client, auth):
    await _login(client)
    comps = []
    for name in ("Кубок Спорт", "Кубок Дебют"):
        comps.append(
            (await client.post(
                "/api/v1/competitions",
                json={"type": "tournament", "name": name, "start_date": str(dt.date(2026, 5, 1))},
                headers=auth,
            )).json()
        )

    r = await client.post(
        "/admin/homepage",
        data={
            "block-1-type": "standings", "block-1-competition_id": str(comps[0]["id"]),
            "block-1-title": "Таблица Спорта",
            # второй слот пустой — пропускается, третий занимает его место
            "block-2-type": "", "block-2-competition_id": "", "block-2-title": "",
            "block-3-type": "bracket", "block-3-competition_id": str(comps[1]["id"]),
            "block-3-title": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text

    body = (await client.get("/api/v1/homepage")).json()
    assert [(b["position"], b["type"], b["competition_id"]) for b in body["blocks"]] == [
        (1, "standings", comps[0]["id"]),
        (2, "bracket", comps[1]["id"]),
    ]
    assert body["blocks"][0]["title"] == "Таблица Спорта"
    assert body["blocks"][1]["title"] is None

    page = await client.get("/admin/homepage")
    assert "Таблица Спорта" in page.text


async def test_admin_protocol_team_stats(client, auth):
    await _login(client)
    a = (await client.post("/api/v1/teams", json={"name": "Ястребы"}, headers=auth)).json()
    b = (await client.post("/api/v1/teams", json={"name": "Барсы"}, headers=auth)).json()
    comp = (await client.post(
        "/api/v1/competitions",
        json={"type": "tournament", "name": "Кубок", "start_date": str(dt.date(2026, 5, 1))},
        headers=auth,
    )).json()
    game = (await client.post(
        "/api/v1/games",
        json={"competition_id": comp["id"], "team_a_id": a["id"], "team_b_id": b["id"],
              "date": str(dt.date(2026, 5, 3))},
        headers=auth,
    )).json()

    r = await client.post(
        f"/admin/games/{game['id']}/protocol",
        data={
            "score_team_a": "7", "score_team_b": "4",
            f"ts-{a['id']}-shots": "41", f"ts-{a['id']}-shots_on_goal": "34",
            f"ts-{a['id']}-faceoffs_won": "9", f"ts-{a['id']}-conversion_percent": "17",
            f"ts-{b['id']}-shots": "37", f"ts-{b['id']}-shots_on_goal": "17",
            f"ts-{b['id']}-faceoffs_won": "16", f"ts-{b['id']}-conversion_percent": "23",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text

    stats = {t["team_id"]: t for t in (await client.get(f"/api/v1/games/{game['id']}")).json()["team_stats"]}
    assert stats[a["id"]]["shots"] == 41
    assert stats[b["id"]]["conversion_percent"] == 23

    # значения вернулись в форму
    page = await client.get(f"/admin/games/{game['id']}/protocol")
    assert 'value="41"' in page.text and "Итоги матча" in page.text

    # ошибка в цифрах не пишет ничего и не теряет введённое
    r = await client.post(
        f"/admin/games/{game['id']}/protocol",
        data={f"ts-{a['id']}-shots": "10", f"ts-{a['id']}-shots_on_goal": "11"},
    )
    assert r.status_code == 200 and "створ" in r.text
    stats = {t["team_id"]: t for t in (await client.get(f"/api/v1/games/{game['id']}")).json()["team_stats"]}
    assert stats[a["id"]]["shots"] == 41
