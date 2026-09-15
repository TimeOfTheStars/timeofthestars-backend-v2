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


# --- командные итоги матча ---
async def test_team_stats_saved_and_penalties_derived(client, auth):
    env = await _setup(client, auth)
    r = await _save(
        client, auth, env,
        [
            {"type": "goal", "team_id": env["a"]["id"], "time_seconds": 600,
             "player_id": env["scorer"]["id"]},
            {"type": "penalty", "team_id": env["a"]["id"], "time_seconds": 900,
             "player_id": env["helper"]["id"], "penalty_minutes": 2},
            {"type": "penalty", "team_id": env["a"]["id"], "time_seconds": 2000,
             "player_id": env["helper"]["id"], "penalty_minutes": 2},
        ],
        score_team_a=1, score_team_b=0,
        team_stats=[
            {"team_id": env["a"]["id"], "shots": 41, "shots_on_goal": 34,
             "faceoffs_won": 9, "conversion_percent": 17},
            {"team_id": env["b"]["id"], "shots": 37, "shots_on_goal": 17,
             "faceoffs_won": 16, "conversion_percent": 23},
        ],
    )
    assert r.status_code == 200, r.text
    stats = {t["team_id"]: t for t in r.json()["team_stats"]}
    assert stats[env["a"]["id"]]["shots"] == 41
    assert stats[env["b"]["id"]]["shots_on_goal"] == 17
    assert stats[env["a"]["id"]]["conversion_percent"] == 17
    # штрафные минуты отдельным полем не хранятся — считаются из событий
    assert stats[env["a"]["id"]]["penalty_minutes"] == 4
    assert stats[env["b"]["id"]]["penalty_minutes"] == 0


async def test_team_stats_none_keeps_previous(client, auth):
    env = await _setup(client, auth)
    await _save(client, auth, env, [], team_stats=[
        {"team_id": env["a"]["id"], "shots": 12},
    ])
    r = await _save(client, auth, env, [])          # team_stats не передан
    assert r.status_code == 200, r.text
    assert [t["shots"] for t in r.json()["team_stats"]] == [12]

    r = await _save(client, auth, env, [], team_stats=[])   # пустой список стирает
    assert r.json()["team_stats"] == []


async def test_team_stats_reject_alien_team_and_duplicates(client, auth):
    env = await _setup(client, auth)
    r = await _save(client, auth, env, [], team_stats=[{"team_id": 999, "shots": 1}])
    assert r.status_code == 400 and "не участвует" in r.json()["detail"]

    r = await _save(client, auth, env, [], team_stats=[
        {"team_id": env["a"]["id"], "shots": 1},
        {"team_id": env["a"]["id"], "shots": 2},
    ])
    assert r.status_code == 400 and "дважды" in r.json()["detail"]


async def test_team_stats_reject_impossible_numbers(client, auth):
    env = await _setup(client, auth)
    # в створ не может быть больше, чем всего
    r = await _save(client, auth, env, [], team_stats=[
        {"team_id": env["a"]["id"], "shots": 10, "shots_on_goal": 11},
    ])
    assert r.status_code == 400 and "створ" in r.json()["detail"]

    for bad in ({"shots": -1}, {"conversion_percent": 101}):
        r = await _save(client, auth, env, [], team_stats=[{"team_id": env["a"]["id"], **bad}])
        assert r.status_code == 422, r.text


# --- моменты голов в карточке игрока ---
VIDEO = "https://vkvideo.ru/live-227828023_456239234"


async def _with_video(client, auth, env, url=VIDEO):
    r = await client.put(f"/api/v1/games/{env['game']['id']}", json={"video_url": url},
                         headers=auth)
    assert r.status_code == 200, r.text


async def _moments(client, player_id):
    r = await client.get(f"/api/v1/players/{player_id}/goal-moments")
    assert r.status_code == 200, r.text
    return r.json()


async def test_goal_moments_only_goals_with_timecode(client, auth):
    env = await _setup(client, auth)
    await _with_video(client, auth, env)
    await _save(
        client, auth, env,
        [
            {"type": "goal", "team_id": env["a"]["id"], "time_seconds": 960,
             "player_id": env["scorer"]["id"], "video_seconds": 2705},
            # второй гол того же игрока без таймкода — в моменты не попадёт
            {"type": "goal", "team_id": env["a"]["id"], "time_seconds": 1800,
             "player_id": env["scorer"]["id"]},
            {"type": "penalty", "team_id": env["a"]["id"], "time_seconds": 900,
             "player_id": env["helper"]["id"], "penalty_minutes": 2},
        ],
        score_team_a=2, score_team_b=0,
    )
    moments = await _moments(client, env["scorer"]["id"])
    assert len(moments) == 1
    m = moments[0]
    assert m["time_seconds"] == 960 and m["video_seconds"] == 2705
    assert m["video_at_url"] == f"{VIDEO}?t=45m5s"
    assert m["video_url"] == VIDEO


async def test_goal_moments_skip_game_without_video(client, auth):
    env = await _setup(client, auth)
    await _save(client, auth, env, [
        {"type": "goal", "team_id": env["a"]["id"], "time_seconds": 960,
         "player_id": env["scorer"]["id"], "video_seconds": 2705},
    ], score_team_a=1, score_team_b=0)
    # видео у матча нет — момент показывать нечем
    assert await _moments(client, env["scorer"]["id"]) == []

    # пустая строка тоже не ссылка
    await _with_video(client, auth, env, url="")
    assert await _moments(client, env["scorer"]["id"]) == []

    await _with_video(client, auth, env)
    assert len(await _moments(client, env["scorer"]["id"])) == 1


async def test_goal_moments_include_shootout_and_skip_assists(client, auth):
    env = await _setup(client, auth)
    await _with_video(client, auth, env)
    await _save(client, auth, env, [
        {"type": "goal", "team_id": env["a"]["id"], "time_seconds": 600,
         "player_id": env["scorer"]["id"], "assist1_player_id": env["helper"]["id"],
         "video_seconds": 120},
        {"type": "shootout_goal", "team_id": env["a"]["id"], "time_seconds": 3600,
         "player_id": env["scorer"]["id"], "video_seconds": 4095},
    ], score_team_a=1, score_team_b=0)

    moments = await _moments(client, env["scorer"]["id"])
    assert [m["type"] for m in moments] == ["goal", "shootout_goal"]
    assert moments[0]["assist1"]["id"] == env["helper"]["id"]
    assert moments[1]["period"] is None                  # у буллита периода нет
    assert moments[1]["video_at_url"] == f"{VIDEO}?t=1h8m15s"
    # ассистенту момент не засчитывается — только собственные голы
    assert await _moments(client, env["helper"]["id"]) == []


async def test_goal_moments_context_from_player_side(client, auth):
    env = await _setup(client, auth)
    await _with_video(client, auth, env)
    await _save(client, auth, env, [
        {"type": "goal", "team_id": env["a"]["id"], "time_seconds": 600,
         "player_id": env["scorer"]["id"], "video_seconds": 120},
        {"type": "goal", "team_id": env["b"]["id"], "time_seconds": 1200,
         "player_id": env["rival"]["id"], "video_seconds": 300},
    ], score_team_a=1, score_team_b=1)

    home = (await _moments(client, env["scorer"]["id"]))[0]
    away = (await _moments(client, env["rival"]["id"]))[0]
    # счёт и соперник — всегда со стороны команды игрока
    assert home["team"]["id"] == env["a"]["id"] and home["opponent"]["id"] == env["b"]["id"]
    assert away["team"]["id"] == env["b"]["id"] and away["opponent"]["id"] == env["a"]["id"]
    assert (home["score_for"], home["score_against"]) == (1, 1)
    assert (away["score_for"], away["score_against"]) == (1, 1)
    assert home["competition_name"] == env["comp"]["name"]
    assert home["date"] == env["game"]["date"]


async def test_goal_moments_newest_game_first(client, auth):
    env = await _setup(client, auth)
    await _with_video(client, auth, env)
    await _save(client, auth, env, [
        {"type": "goal", "team_id": env["a"]["id"], "time_seconds": 1800,
         "player_id": env["scorer"]["id"], "video_seconds": 300},
        {"type": "goal", "team_id": env["a"]["id"], "time_seconds": 600,
         "player_id": env["scorer"]["id"], "video_seconds": 120},
    ], score_team_a=2, score_team_b=0)

    later = (await client.post("/api/v1/games", json={
        "competition_id": env["comp"]["id"], "team_a_id": env["a"]["id"],
        "team_b_id": env["b"]["id"], "date": str(dt.date(2026, 4, 1)),
        "video_url": VIDEO,
    }, headers=auth)).json()
    r = await client.put(
        f"/api/v1/games/{later['id']}/protocol",
        json={"stat_lines": [{"player_id": env["scorer"]["id"], "team_id": env["a"]["id"]}],
              "events": [{"type": "goal", "team_id": env["a"]["id"], "time_seconds": 60,
                          "player_id": env["scorer"]["id"], "video_seconds": 30}],
              "score_team_a": 1, "score_team_b": 0},
        headers=auth,
    )
    assert r.status_code == 200, r.text

    moments = await _moments(client, env["scorer"]["id"])
    # свежий матч сверху, внутри матча — по игровому времени
    assert [m["game_id"] for m in moments] == [later["id"], env["game"]["id"], env["game"]["id"]]
    assert [m["time_seconds"] for m in moments] == [60, 600, 1800]


async def test_goal_moments_survive_deleted_assistant(client, auth):
    env = await _setup(client, auth)
    await _with_video(client, auth, env)
    await _save(client, auth, env, [
        {"type": "goal", "team_id": env["a"]["id"], "time_seconds": 600,
         "player_id": env["scorer"]["id"], "assist1_player_id": env["helper"]["id"],
         "video_seconds": 120},
    ], score_team_a=1, score_team_b=0)

    assert (await client.delete(f"/api/v1/players/{env['helper']['id']}",
                                headers=auth)).status_code == 204
    moments = await _moments(client, env["scorer"]["id"])
    # ассистент уходит по SET NULL, сам гол остаётся
    assert len(moments) == 1 and moments[0]["assist1"] is None


async def test_goal_moments_empty_and_unknown_player(client, auth):
    env = await _setup(client, auth)
    assert await _moments(client, env["keeper"]["id"]) == []      # голов нет — пустой список
    r = await client.get("/api/v1/players/424242/goal-moments")
    assert r.status_code == 404


@pytest.mark.parametrize("seconds,tail", [
    (0, "0s"), (45, "45s"), (65, "1m5s"), (2705, "45m5s"),
    (3665, "1h1m5s"), (4095, "1h8m15s"),
])
def test_video_url_at_matches_frontend_format(seconds, tail):
    from app.services.clock import parse_video_time, video_url_at

    link = video_url_at(VIDEO, seconds)
    assert link == f"{VIDEO}?t={tail}"
    # обратный разбор живёт в том же модуле — значение не искажается
    assert parse_video_time(link) == seconds


def test_video_url_at_keeps_existing_query_and_handles_gaps():
    from app.services.clock import video_url_at

    assert video_url_at("https://vk.ru/video?z=1", 2705) == "https://vk.ru/video?z=1&t=45m5s"
    assert video_url_at(None, 10) is None
    assert video_url_at(VIDEO, None) is None
