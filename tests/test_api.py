import datetime as dt


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_auth_required_for_writes(client):
    # без токена запись запрещена
    r = await client.post("/api/v1/teams", json={"name": "X"})
    assert r.status_code == 401
    # чтение публичное
    r = await client.get("/api/v1/teams")
    assert r.status_code == 200


async def test_me(client, auth):
    r = await client.get("/api/v1/auth/me", headers=auth)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


async def _make_team(client, auth, name):
    r = await client.post("/api/v1/teams", json={"name": name, "city": "Москва"}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


async def _make_player(client, auth, name, position="нападающий"):
    r = await client.post(
        "/api/v1/players", json={"full_name": name, "position": position}, headers=auth
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_full_flow_standings_and_player_stats(client, auth):
    a = await _make_team(client, auth, "Сокол")
    b = await _make_team(client, auth, "Молния")
    p1 = await _make_player(client, auth, "Иван Петров")
    p2 = await _make_player(client, auth, "Сергей Смирнов")
    p3 = await _make_player(client, auth, "Пётр Голкипер", "вратарь")
    p4 = await _make_player(client, auth, "Олег Крайний")

    # соревнование
    r = await client.post(
        "/api/v1/competitions",
        json={
            "type": "championship",
            "name": "Кубок",
            "start_date": str(dt.date(2026, 1, 1)),
            "show_best_players": True,
        },
        headers=auth,
    )
    assert r.status_code == 201, r.text
    comp = r.json()

    # состав
    for pid, tid in [
        (p1["id"], a["id"]),
        (p3["id"], a["id"]),
        (p4["id"], a["id"]),
        (p2["id"], b["id"]),
    ]:
        rr = await client.post(
            f"/api/v1/competitions/{comp['id']}/players",
            json={"team_id": tid, "player_id": pid, "number": 9, "contract": True},
            headers=auth,
        )
        assert rr.status_code == 204, rr.text

    # матч
    r = await client.post(
        "/api/v1/games",
        json={
            "competition_id": comp["id"],
            "team_a_id": a["id"],
            "team_b_id": b["id"],
            "date": str(dt.date(2026, 1, 5)),
        },
        headers=auth,
    )
    assert r.status_code == 201, r.text
    game = r.json()

    # Протокол: A 3 : 2 B. Голы и передачи задаются событиями таймлайна,
    # в строках участия их больше не передают — сервер считает сам.
    r = await client.put(
        f"/api/v1/games/{game['id']}/protocol",
        json={
            "score_team_a": 3,
            "score_team_b": 2,
            "stat_lines": [
                {"player_id": p1["id"], "team_id": a["id"]},
                {"player_id": p4["id"], "team_id": a["id"]},
                {"player_id": p3["id"], "team_id": a["id"], "is_goalie": True,
                 "goals_against": 2, "saves": 20, "minutes_played": 60},
                {"player_id": p2["id"], "team_id": b["id"]},
            ],
            "events": [
                {"type": "goalie_change", "team_id": a["id"], "time_seconds": 0,
                 "player_id": p3["id"]},
                {"type": "goal", "team_id": a["id"], "time_seconds": 300,
                 "player_id": p1["id"], "video_seconds": 2705},
                {"type": "goal", "team_id": b["id"], "time_seconds": 900,
                 "player_id": p2["id"]},
                {"type": "goal", "team_id": a["id"], "time_seconds": 1500,
                 "player_id": p1["id"]},
                {"type": "goal", "team_id": a["id"], "time_seconds": 2700,
                 "player_id": p4["id"], "assist1_player_id": p1["id"]},
                {"type": "goal", "team_id": b["id"], "time_seconds": 3000,
                 "player_id": p2["id"]},
            ],
        },
        headers=auth,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "finished"
    assert len(r.json()["player_stats"]) == 4
    # события вернулись отсортированными по времени
    assert [e["time_seconds"] for e in r.json()["events"]] == [0, 300, 900, 1500, 2700, 3000]
    # цифры выведены из событий, а не приняты извне
    by_player = {s["player_id"]: s for s in r.json()["player_stats"]}
    assert by_player[p1["id"]]["goals"] == 2
    assert by_player[p1["id"]]["assists"] == 1
    assert by_player[p4["id"]]["goals"] == 1

    # турнирная таблица
    r = await client.get(f"/api/v1/competitions/{comp['id']}/standings")
    assert r.status_code == 200
    standings = {row["team"]["name"]: row for row in r.json()}
    assert standings["Сокол"]["wins"] == 1
    assert standings["Сокол"]["points"] == 2
    assert standings["Молния"]["losses"] == 1
    assert standings["Сокол"]["goals_scored"] == 3
    assert standings["Сокол"]["goals_conceded"] == 2

    # статистика игрока
    r = await client.get(f"/api/v1/players/{p1['id']}/stats")
    assert r.status_code == 200
    car = r.json()["career"]
    assert car["goals"] == 2 and car["assists"] == 1 and car["points"] == 3
    assert r.json()["by_competition"][0]["competition_id"] == comp["id"]

    # лучшие игроки
    r = await client.get(f"/api/v1/competitions/{comp['id']}/best-players")
    assert r.status_code == 200
    best = r.json()
    assert best[0]["player"]["id"] == p1["id"]
    assert best[0]["points"] == 3


async def test_change_player_number_and_contract(client, auth):
    a = await _make_team(client, auth, "Витязь")
    p = await _make_player(client, auth, "Роман Игроков")
    r = await client.post(
        "/api/v1/competitions",
        json={"type": "championship", "name": "Лига", "start_date": str(dt.date(2026, 4, 1))},
        headers=auth,
    )
    comp = r.json()
    rr = await client.post(
        f"/api/v1/competitions/{comp['id']}/players",
        json={"team_id": a["id"], "player_id": p["id"], "number": 10, "contract": False},
        headers=auth,
    )
    assert rr.status_code == 204

    # сменить номер и контракт
    r = await client.patch(
        f"/api/v1/competitions/{comp['id']}/players/{p['id']}",
        json={"team_id": a["id"], "number": 77, "contract": True},
        headers=auth,
    )
    assert r.status_code == 204, r.text

    players = (await client.get(f"/api/v1/competitions/{comp['id']}/players")).json()
    me = next(x for x in players if x["player"]["id"] == p["id"])
    assert me["number"] == 77
    assert me["contract"] is True

    # запрос без токена запрещён
    r = await client.patch(
        f"/api/v1/competitions/{comp['id']}/players/{p['id']}",
        json={"team_id": a["id"], "number": 5},
    )
    assert r.status_code == 401


async def test_bullet_win_gives_extra_point(client, auth):
    a = await _make_team(client, auth, "Барс")
    b = await _make_team(client, auth, "Комета")
    r = await client.post(
        "/api/v1/competitions",
        json={"type": "tournament", "name": "Т", "start_date": str(dt.date(2026, 2, 1))},
        headers=auth,
    )
    comp = r.json()
    for tid in (a["id"], b["id"]):
        await client.post(
            f"/api/v1/competitions/{comp['id']}/teams", json={"team_id": tid}, headers=auth
        )
    r = await client.post(
        "/api/v1/games",
        json={
            "competition_id": comp["id"],
            "team_a_id": a["id"],
            "team_b_id": b["id"],
            "date": str(dt.date(2026, 2, 3)),
            "score_team_a": 2,
            "score_team_b": 2,
            "bullet_win_team_id": a["id"],
        },
        headers=auth,
    )
    assert r.status_code == 201, r.text
    r = await client.get(f"/api/v1/competitions/{comp['id']}/standings")
    standings = {row["team"]["name"]: row for row in r.json()}
    # победитель буллитов: 2 очка (ничья 1 + доп 1), проигравший — 1
    assert standings["Барс"]["points"] == 2
    assert standings["Барс"]["extra_points"] == 1
    assert standings["Комета"]["points"] == 1


async def test_playoff_game_excluded_from_standings(client, auth):
    a = await _make_team(client, auth, "Орлы")
    b = await _make_team(client, auth, "Тигры")
    r = await client.post(
        "/api/v1/competitions",
        json={"type": "championship", "name": "ЧП", "start_date": str(dt.date(2026, 3, 1))},
        headers=auth,
    )
    comp = r.json()
    for tid in (a["id"], b["id"]):
        await client.post(
            f"/api/v1/competitions/{comp['id']}/teams", json={"team_id": tid}, headers=auth
        )
    # матч плей-офф не должен влиять на таблицу
    await client.post(
        "/api/v1/games",
        json={
            "competition_id": comp["id"],
            "team_a_id": a["id"],
            "team_b_id": b["id"],
            "date": str(dt.date(2026, 3, 5)),
            "score_team_a": 5,
            "score_team_b": 0,
            "stage": "final",
        },
        headers=auth,
    )
    r = await client.get(f"/api/v1/competitions/{comp['id']}/standings")
    standings = {row["team"]["name"]: row for row in r.json()}
    assert standings["Орлы"]["games"] == 0
    assert standings["Орлы"]["points"] == 0
