"""Таймлайн матча: вывод статистики из событий и валидация."""
import datetime as dt

import pytest

from app.models.game import period_from_seconds


async def _setup(client, auth):
    """Матч двух команд с составом: A — два игрока и вратарь, B — один игрок."""
    async def post(path, payload, expect=201):
        r = await client.post(path, json=payload, headers=auth)
        assert r.status_code == expect, r.text
        return r.json() if expect != 204 else None

    a = await post("/api/v1/teams", {"name": "Альфа"})
    b = await post("/api/v1/teams", {"name": "Бета"})
    scorer = await post("/api/v1/players", {"full_name": "Автор Голов"})
    helper = await post("/api/v1/players", {"full_name": "Ассистент Пасов"})
    keeper = await post("/api/v1/players", {"full_name": "Вратарь Первый", "position": "вратарь"})
    rival = await post("/api/v1/players", {"full_name": "Соперник Единственный"})
    comp = await post(
        "/api/v1/competitions",
        {"type": "tournament", "name": "Тест-кубок", "start_date": str(dt.date(2026, 3, 1))},
    )
    for pid, tid in (
        (scorer["id"], a["id"]),
        (helper["id"], a["id"]),
        (keeper["id"], a["id"]),
        (rival["id"], b["id"]),
    ):
        await post(
            f"/api/v1/competitions/{comp['id']}/players",
            {"team_id": tid, "player_id": pid},
            expect=204,
        )
    game = await post(
        "/api/v1/games",
        {
            "competition_id": comp["id"],
            "team_a_id": a["id"],
            "team_b_id": b["id"],
            "date": str(dt.date(2026, 3, 2)),
        },
    )
    lines = [
        {"player_id": scorer["id"], "team_id": a["id"]},
        {"player_id": helper["id"], "team_id": a["id"]},
        {"player_id": keeper["id"], "team_id": a["id"], "is_goalie": True,
         "goals_against": 1, "saves": 15, "minutes_played": 60},
        {"player_id": rival["id"], "team_id": b["id"]},
    ]
    return {
        "comp": comp, "game": game, "a": a, "b": b, "lines": lines,
        "scorer": scorer, "helper": helper, "keeper": keeper, "rival": rival,
    }


async def _save(client, auth, env, events, **over):
    payload = {"stat_lines": env["lines"], **over}
    if events is not None:
        payload["events"] = events
    return await client.put(
        f"/api/v1/games/{env['game']['id']}/protocol", json=payload, headers=auth
    )


async def test_totals_are_derived_from_events(client, auth):
    env = await _setup(client, auth)
    r = await _save(
        client, auth, env,
        [
            {"type": "goal", "team_id": env["a"]["id"], "time_seconds": 600,
             "player_id": env["scorer"]["id"], "assist1_player_id": env["helper"]["id"]},
            {"type": "goal", "team_id": env["a"]["id"], "time_seconds": 1800,
             "player_id": env["scorer"]["id"]},
            {"type": "penalty", "team_id": env["a"]["id"], "time_seconds": 900,
             "player_id": env["helper"]["id"], "penalty_minutes": 2},
            {"type": "penalty", "team_id": env["a"]["id"], "time_seconds": 2000,
             "player_id": env["helper"]["id"], "penalty_minutes": 2},
        ],
        score_team_a=2, score_team_b=0,
    )
    assert r.status_code == 200, r.text
    stats = {s["player_id"]: s for s in r.json()["player_stats"]}
    assert stats[env["scorer"]["id"]]["goals"] == 2
    assert stats[env["helper"]["id"]]["assists"] == 1
    # penalties — это МИНУТЫ, а не число удалений
    assert stats[env["helper"]["id"]]["penalties"] == 4
    # вратарские цифры остались ручными
    assert stats[env["keeper"]["id"]]["saves"] == 15


async def test_shootout_goal_out_of_score_but_in_personal_stats(client, auth):
    env = await _setup(client, auth)
    r = await _save(
        client, auth, env,
        [
            {"type": "goal", "team_id": env["b"]["id"], "time_seconds": 1000,
             "player_id": env["rival"]["id"]},
            {"type": "goal", "team_id": env["a"]["id"], "time_seconds": 2000,
             "player_id": env["scorer"]["id"]},
            {"type": "shootout_goal", "team_id": env["a"]["id"], "time_seconds": 3600,
             "player_id": env["scorer"]["id"]},
        ],
        score_team_a=1, score_team_b=1, bullet_win_team_id=env["a"]["id"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # в счёт матча буллит не идёт: обычных голов у A ровно один
    regular = [e for e in body["events"] if e["type"] == "goal" and e["team_id"] == env["a"]["id"]]
    assert len(regular) == body["score_team_a"] == 1
    # а в личную статистику идёт
    stats = {s["player_id"]: s for s in body["player_stats"]}
    assert stats[env["scorer"]["id"]]["goals"] == 2
    # у буллита нет периода
    shootout = [e for e in body["events"] if e["type"] == "shootout_goal"][0]
    assert shootout["period"] is None
    # таблица считает ничью плюс дополнительный балл
    r = await client.get(f"/api/v1/competitions/{env['comp']['id']}/standings")
    rows = {row["team"]["name"]: row for row in r.json()}
    assert rows["Альфа"]["draws"] == 1
    assert rows["Альфа"]["points"] == 2
    assert rows["Бета"]["points"] == 1


@pytest.mark.parametrize(
    "mutate, expected_fragment",
    [
        (lambda e, env: e.update(team_id=999), "не участвует"),
        (lambda e, env: e.update(player_id=env["rival"]["id"]), "за другую команду"),
        (lambda e, env: e.update(assist1_player_id=e["player_id"]), "своим же ассистентом"),
        (lambda e, env: e.update(
            assist1_player_id=env["helper"]["id"], assist2_player_id=env["helper"]["id"]
        ), "на одного игрока"),
        (lambda e, env: e.update(assist2_player_id=env["helper"]["id"]), "без первой"),
        (lambda e, env: e.update(penalty_minutes=2), "не относятся к голу"),
    ],
)
async def test_event_validation_rejects(client, auth, mutate, expected_fragment):
    env = await _setup(client, auth)
    event = {
        "type": "goal", "team_id": env["a"]["id"], "time_seconds": 600,
        "player_id": env["scorer"]["id"],
    }
    mutate(event, env)
    r = await _save(client, auth, env, [event])
    assert r.status_code == 400, r.text
    assert expected_fragment in r.json()["detail"], r.json()["detail"]


async def test_goalie_change_requires_goalie_flag(client, auth):
    env = await _setup(client, auth)
    r = await _save(
        client, auth, env,
        [{"type": "goalie_change", "team_id": env["a"]["id"], "time_seconds": 0,
          "player_id": env["scorer"]["id"]}],
    )
    assert r.status_code == 400
    assert "не отмечен вратарём" in r.json()["detail"]


async def test_empty_net_event(client, auth):
    """Пустые ворота: player_id — вратарь, который ушёл с площадки."""
    env = await _setup(client, auth)
    r = await _save(
        client, auth, env,
        [
            {"type": "goalie_change", "team_id": env["a"]["id"], "time_seconds": 0,
             "player_id": env["keeper"]["id"]},
            {"type": "empty_net", "team_id": env["a"]["id"], "time_seconds": 2880,
             "player_id": env["keeper"]["id"]},
            {"type": "goalie_change", "team_id": env["a"]["id"], "time_seconds": 2890,
             "player_id": env["keeper"]["id"]},
        ],
    )
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert [e["type"] for e in events] == ["goalie_change", "empty_net", "goalie_change"]
    # у события есть обычный период, штрафа и передач нет
    empty = events[1]
    assert empty["period"] == 3
    assert empty["penalty_minutes"] is None
    assert empty["assist1_player_id"] is None
    # на статистику не влияет
    stats = {s["player_id"]: s for s in r.json()["player_stats"]}
    assert stats[env["keeper"]["id"]]["goals"] == 0


async def test_empty_net_requires_goalie(client, auth):
    env = await _setup(client, auth)
    r = await _save(
        client, auth, env,
        [{"type": "empty_net", "team_id": env["a"]["id"], "time_seconds": 2880,
          "player_id": env["scorer"]["id"]}],
    )
    assert r.status_code == 400
    assert "не отмечен вратарём" in r.json()["detail"]


async def test_player_without_stat_line_is_rejected(client, auth):
    env = await _setup(client, auth)
    env["lines"] = [line for line in env["lines"] if line["player_id"] != env["scorer"]["id"]]
    r = await _save(
        client, auth, env,
        [{"type": "goal", "team_id": env["a"]["id"], "time_seconds": 600,
          "player_id": env["scorer"]["id"]}],
    )
    assert r.status_code == 400
    assert "отсутствует в протоколе" in r.json()["detail"]


async def test_omitting_events_keeps_timeline(client, auth):
    env = await _setup(client, auth)
    events = [
        {"type": "goal", "team_id": env["a"]["id"], "time_seconds": 600,
         "player_id": env["scorer"]["id"], "assist1_player_id": env["helper"]["id"]}
    ]
    assert (await _save(client, auth, env, events, score_team_a=1, score_team_b=0)).status_code == 200

    # повторное сохранение без ключа events не должно стереть таймлайн
    r = await _save(client, auth, env, None, score_team_a=1, score_team_b=0)
    assert r.status_code == 200, r.text
    assert len(r.json()["events"]) == 1
    stats = {s["player_id"]: s for s in r.json()["player_stats"]}
    assert stats[env["scorer"]["id"]]["goals"] == 1
    assert stats[env["helper"]["id"]]["assists"] == 1


async def test_empty_events_clears_timeline(client, auth):
    env = await _setup(client, auth)
    await _save(
        client, auth, env,
        [{"type": "goal", "team_id": env["a"]["id"], "time_seconds": 600,
          "player_id": env["scorer"]["id"]}],
    )
    r = await _save(client, auth, env, [])
    assert r.status_code == 200, r.text
    assert r.json()["events"] == []
    assert all(s["goals"] == 0 for s in r.json()["player_stats"])


async def test_dropping_player_orphans_existing_event(client, auth):
    """Состав переписали без автора гола, события не прислали — это должно упасть."""
    env = await _setup(client, auth)
    await _save(
        client, auth, env,
        [{"type": "goal", "team_id": env["a"]["id"], "time_seconds": 600,
          "player_id": env["scorer"]["id"]}],
    )
    env["lines"] = [line for line in env["lines"] if line["player_id"] != env["scorer"]["id"]]
    r = await _save(client, auth, env, None)
    assert r.status_code == 400
    assert "отсутствует в протоколе" in r.json()["detail"]


async def test_timeline_order_and_periods(client, auth):
    env = await _setup(client, auth)
    a = env["a"]["id"]
    # присылаем не по порядку; два события с одинаковым временем
    r = await _save(
        client, auth, env,
        [
            {"type": "goal", "team_id": a, "time_seconds": 3600, "player_id": env["scorer"]["id"]},
            {"type": "goal", "team_id": a, "time_seconds": 1200, "player_id": env["scorer"]["id"]},
            {"type": "penalty", "team_id": a, "time_seconds": 3600,
             "player_id": env["helper"]["id"], "penalty_minutes": 2},
            {"type": "goal", "team_id": a, "time_seconds": 1201, "player_id": env["helper"]["id"]},
        ],
    )
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert [e["time_seconds"] for e in events] == [1200, 1201, 3600, 3600]
    # при равном времени сохраняется порядок присланного массива
    assert [e["type"] for e in events[2:]] == ["goal", "penalty"]
    assert [e["period"] for e in events] == [1, 2, 3, 3]
    # конец удаления выводится из начала и минут
    penalty = events[3]
    assert penalty["penalty_end_seconds"] == 3600 + 120


@pytest.mark.parametrize(
    "seconds, period",
    [(0, 1), (1, 1), (1200, 1), (1201, 2), (2400, 2), (2401, 3), (3600, 3), (3601, 4), (5000, 4)],
)
def test_period_boundaries(seconds, period):
    assert period_from_seconds(seconds) == period


async def test_deleting_game_removes_events(client, auth):
    env = await _setup(client, auth)
    await _save(
        client, auth, env,
        [{"type": "goal", "team_id": env["a"]["id"], "time_seconds": 600,
          "player_id": env["scorer"]["id"]}],
    )
    r = await client.delete(f"/api/v1/games/{env['game']['id']}", headers=auth)
    assert r.status_code == 204, r.text

    from sqlalchemy import func, select

    from app.db.session import async_session_maker
    from app.models import GameEvent

    async with async_session_maker() as db:
        left = await db.scalar(select(func.count()).select_from(GameEvent))
    assert left == 0
