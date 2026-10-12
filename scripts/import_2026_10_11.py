# -*- coding: utf-8 -*-
"""Протокол матча 11.10.2026 — игра 25 (Дебют), полуфинал.

Кристалл (A) — Железный Феникс (B), 2:5. Источник — ~/Downloads/11_10_2026.docx.

Бумага сходится по всем контрольным строкам:
  * «Взятие ворот» по периодам: А 1-0-1 (всего 2), Б 2-2-1 (всего 5);
  * «Штрафное время» по периодам: А 2-8 (всего 10), Б 6-10 (всего 16);
  * удаление Феникса 09:39-11:25 закрылось ровно голом Кристалла на 11:25
    (в графе ИС у этого гола стоит «+1» — большинство);
  * «Время игры вратарей»: оба №1 от 00:00 до 60:00.

Решения заказчика:
  * №33 «Никифоров Роман» из бумаги — это Никифоров Руслан из заявки;
  * №20 Власов Артем и №2 Шиханов Клим создаются без даты рождения;
  * время матча ставим 10:05 («Начало игры» из протокола), в базе было 00:00.

Опечатки и сокращения бумаги (разобраны по номерам из заявки соревнования 3):
  * «Павлихин Иван» №1 — Повалихин Иван;
  * «Максим» №11 — Маров Максим; «Игорь» №75 — Яныгин Игорь;
  * «Анатолий» №98 — Палитов Анатолий; «Михаил» №42 — Игнаткин Михаил;
  * «Алексей» №10 (Вр) — Чувачко Алексей, в протоколе отметка «Иг: нет»,
    поэтому в состав матча НЕ вносится (иначе зачтётся проведённая игра).

Заявку соревнования не правим: номера в ней остаются как есть, никого не
удаляем. Двое новых игроков в заявку добавляются — иначе протокол не внести.

    PYTHONPATH=/app python /tmp/import_1110.py --dry-run
    PYTHONPATH=/app python /tmp/import_1110.py --apply
"""

import asyncio
import datetime as dt
import sys

from sqlalchemy import select

from app.models import CompetitionPlayer, Player
from app.models.enums import GameEventType, PlayerPosition
from app.schemas.game import GameEventIn, GameUpdate, PlayerStatLine, ProtocolRequest
from app.schemas.player import PlayerCreate
from app.services import competition_service, game_service, player_service

G, P, GC = GameEventType.goal, GameEventType.penalty, GameEventType.goalie_change

GAME_ID = 25
COMP = 3                      # Летний Кубок (Дебют)
KRISTALL, FENIKS = 17, 18
START_TIME = dt.time(10, 5)   # «Начало игры» из протокола

# Игроков нет в базе совсем — создаём и дозаявляем. Номер берём из протокола:
# взять его больше негде, а без заявки строку участия не записать.
NEW_PLAYERS = [
    ("Власов Артем", PlayerPosition.forward, KRISTALL, 20),
    ("Шиханов Клим", PlayerPosition.forward, FENIKS, 2),
]

# ключ — номер из протокола, значение — имя в базе
LINEUPS = {
    KRISTALL: {
        1: "Повалихин Иван", 11: "Маров Максим", 12: "Шахаров Сергей",
        13: "Власов Илья", 15: "Мартыненко Никита", 17: "Чистяков Даниил",
        18: "Капустин Михаил", 20: "Власов Артем", 23: "Блохин Роман",
        24: "Зуев Роман", 26: "Каюров Андрей", 29: "Кузнецов Павел",
        33: "Никифоров Руслан", 75: "Яныгин Игорь", 93: "Сафронов Александр",
        97: "Смирнов Николай", 98: "Палитов Анатолий",
    },
    FENIKS: {
        1: "Пашинцев Максим", 2: "Шиханов Клим", 29: "Сентюрин Николай",
        42: "Игнаткин Михаил", 54: "Смирнов Савелий", 55: "Доценко Владимир",
        64: "Степанов Сергей", 69: "Мартюшов Кирилл", 70: "Радченко Алексей",
        76: "Ильин Артем", 77: "Мельников Павел", 87: "Степанов Роман",
        88: "Губанов Андрей", 92: "Солнцев Владислав", 98: "Тюренков Вячеслав",
    },
}

SCORE = {KRISTALL: 2, FENIKS: 5}
# оба вратаря отыграли всю игру: (пропущено, минут)
GOALIES = {KRISTALL: {1: (5, 60)}, FENIKS: {1: (2, 60)}}
EXPECT_PERIODS = {KRISTALL: [1, 0, 1], FENIKS: [2, 2, 1]}
EXPECT_PIM = {KRISTALL: 10, FENIKS: 16}

# (мин, сек, тип, команда, №, пас1, пас2, минуты штрафа)
EVENTS = [
    (0, 0, GC, KRISTALL, 1, None, None, None),
    (0, 0, GC, FENIKS, 1, None, None, None),
    (2, 10, G, FENIKS, 54, 70, None, None),
    (7, 30, G, FENIKS, 55, None, None, None),
    (9, 39, P, FENIKS, 64, None, None, 2),
    (11, 25, G, KRISTALL, 24, None, None, None),   # в большинстве, ИС «+1»
    (16, 50, P, FENIKS, 92, None, None, 2),
    (18, 20, P, FENIKS, 64, None, None, 2),
    (18, 55, P, KRISTALL, 15, None, None, 2),
    (20, 0, P, FENIKS, 54, None, None, 2),
    (24, 47, P, KRISTALL, 98, None, None, 4),      # потасовка: по два игрока с каждой
    (24, 47, P, KRISTALL, 75, None, None, 4),      # стороны получили по 4 минуты
    (24, 47, P, FENIKS, 98, None, None, 4),
    (24, 47, P, FENIKS, 55, None, None, 4),
    (33, 40, G, FENIKS, 55, 64, None, None),
    (37, 43, G, FENIKS, 55, 98, None, None),
    (43, 35, G, FENIKS, 55, 77, None, None),
    (58, 58, G, KRISTALL, 97, 13, 24, None),
]


def period(sec: int) -> int:
    return 1 if sec <= 0 else min((sec - 1) // 1200 + 1, 3)


async def ensure_players(db, apply: bool) -> None:
    """Создаёт отсутствующих игроков и дозаявляет их. Идемпотентно."""
    print("=== новые игроки ===")
    for name, position, team_id, number in NEW_PLAYERS:
        found = (await db.execute(select(Player).where(Player.full_name == name))).scalars().all()
        if len(found) > 1:
            raise SystemExit(f"«{name}» в базе {len(found)} раз — нужен разбор")
        player = found[0] if found else None
        if player is None:
            print(f"  создаём «{name}» ({position.value}) -> команда {team_id}, №{number}")
            if apply:
                player = await player_service.create(
                    db, PlayerCreate(full_name=name, position=position)
                )
        else:
            print(f"  «{name}» уже есть, id={player.id}")

        if player is None:          # dry-run, игрока ещё нет
            continue
        in_roster = (await db.execute(
            select(CompetitionPlayer.id).where(
                CompetitionPlayer.competition_id == COMP,
                CompetitionPlayer.team_id == team_id,
                CompetitionPlayer.player_id == player.id,
            )
        )).first()
        if in_roster is None:
            print(f"    дозаявляем в соревнование {COMP}, команда {team_id}, №{number}")
            if apply:
                await competition_service.add_player(
                    db, COMP, team_id, player.id, number=number, contract=False
                )
        else:
            print("    в заявке уже есть")


async def resolve(db, team_id: int, apply: bool) -> dict[int, Player]:
    rows = (await db.execute(
        select(Player)
        .join(CompetitionPlayer, CompetitionPlayer.player_id == Player.id)
        .where(CompetitionPlayer.competition_id == COMP,
               CompetitionPlayer.team_id == team_id)
    )).scalars().all()
    by_name: dict[str, list[Player]] = {}
    for p in rows:
        by_name.setdefault(p.full_name, []).append(p)

    new_names = {name for name, _pos, tid, _n in NEW_PLAYERS if tid == team_id}
    out: dict[int, Player] = {}
    for number, name in LINEUPS[team_id].items():
        hits = by_name.get(name, [])
        if len(hits) > 1:
            raise SystemExit(f"в заявке {team_id} «{name}» {len(hits)} раз — нужен разбор")
        if not hits:
            if not apply and name in new_names:
                continue            # в dry-run этого игрока ещё не создали
            raise SystemExit(f"НЕ НАЙДЕН в заявке {team_id}: {name} (№{number})")
        out[number] = hits[0]
    return out


async def process(db, apply: bool) -> tuple[int, int]:
    game = await game_service.get_with_protocol(db, GAME_ID)
    if game is None:
        raise SystemExit(f"игра {GAME_ID} не найдена")
    if (game.team_a_id, game.team_b_id) != (KRISTALL, FENIKS):
        raise SystemExit(f"игра {GAME_ID}: в базе {game.team_a_id} vs {game.team_b_id}")
    if game.date != dt.date(2026, 10, 11):
        raise SystemExit(f"игра {GAME_ID}: дата в базе {game.date}")
    print(f"\n=== игра {GAME_ID}: {game.date} {game.time}, сейчас "
          f"{game.score_team_a}:{game.score_team_b}, строк {len(game.player_stats)}, "
          f"событий {len(game.events)}, стадия {game.stage.value} ===")

    rosters = {tid: await resolve(db, tid, apply) for tid in (KRISTALL, FENIKS)}

    lines = []
    for team_id in (KRISTALL, FENIKS):
        for number in LINEUPS[team_id]:
            player = rosters[team_id].get(number)
            if player is None:
                continue            # только dry-run по ещё не созданным
            extra = {}
            if number in GOALIES[team_id]:
                against, minutes = GOALIES[team_id][number]
                extra = dict(is_goalie=True, goals_against=against, minutes_played=minutes)
            lines.append(PlayerStatLine(player_id=player.id, team_id=team_id, **extra))

    events = []
    for mm, ss, etype, team_id, num, a1, a2, pim in EVENTS:
        mapping = rosters[team_id]
        if any(n is not None and n not in mapping for n in (num, a1, a2)):
            if not apply:
                continue            # dry-run без ещё не созданных игроков
            raise SystemExit(f"нет №{num}/{a1}/{a2} в составе команды {team_id}")
        events.append(GameEventIn(
            type=etype, team_id=team_id, time_seconds=mm * 60 + ss,
            player_id=mapping[num].id,
            assist1_player_id=mapping[a1].id if a1 is not None else None,
            assist2_player_id=mapping[a2].id if a2 is not None else None,
            penalty_minutes=pim,
        ))

    goals = {KRISTALL: 0, FENIKS: 0}
    per = {KRISTALL: [0, 0, 0], FENIKS: [0, 0, 0]}
    pim = {KRISTALL: 0, FENIKS: 0}
    for ev in events:
        if ev.type is GameEventType.goal:
            goals[ev.team_id] += 1
            per[ev.team_id][period(ev.time_seconds) - 1] += 1
        elif ev.type is GameEventType.penalty:
            pim[ev.team_id] += ev.penalty_minutes

    print(f"  голов {goals[KRISTALL]}:{goals[FENIKS]}, ставим счёт "
          f"{SCORE[KRISTALL]}:{SCORE[FENIKS]}")
    print(f"  периоды {KRISTALL}: {per[KRISTALL]} (бумага {EXPECT_PERIODS[KRISTALL]}), "
          f"{FENIKS}: {per[FENIKS]} (бумага {EXPECT_PERIODS[FENIKS]})")
    print(f"  штраф {pim[KRISTALL]}:{pim[FENIKS]} "
          f"(бумага {EXPECT_PIM[KRISTALL]}:{EXPECT_PIM[FENIKS]})")
    print(f"  строк участия {len(lines)}, событий {len(events)}")
    print(f"  время матча {game.time} -> {START_TIME}")

    if not apply:
        print("  (в dry-run двух новых игроков ещё нет, поэтому строк на 2 меньше)")
        return len(lines) + 2, len(events)

    assert goals[KRISTALL] == SCORE[KRISTALL] and goals[FENIKS] == SCORE[FENIKS], "счёт"
    assert per[KRISTALL] == EXPECT_PERIODS[KRISTALL], "периоды хозяев"
    assert per[FENIKS] == EXPECT_PERIODS[FENIKS], "периоды гостей"
    assert pim == EXPECT_PIM, "штраф"

    await game_service.save_protocol(db, game, ProtocolRequest(
        score_team_a=SCORE[KRISTALL], score_team_b=SCORE[FENIKS],
        bullet_win_team_id=None,
        stat_lines=lines, events=events, team_stats=None,
    ))
    await game_service.update(db, game, GameUpdate(time=START_TIME))
    print("  записано")
    return len(lines), len(events)


async def main(apply: bool) -> None:
    from app.db.session import async_session_maker

    async with async_session_maker() as db:
        await ensure_players(db, apply)
        if apply:
            await db.flush()
        n_lines, n_events = await process(db, apply)
        if apply:
            await db.commit()
        else:
            print("\n--- dry-run, ничего не записано ---")
            return

    async with async_session_maker() as db:
        game = await game_service.get_with_protocol(db, GAME_ID)
        assert len(game.player_stats) == n_lines, f"строки: {len(game.player_stats)} != {n_lines}"
        assert len(game.events) == n_events, f"события: {len(game.events)} != {n_events}"
        print(f"\n  игра {GAME_ID}: {game.date} {game.time}, "
              f"{game.score_team_a}:{game.score_team_b}, строк {len(game.player_stats)}, "
              f"событий {len(game.events)}, статус {game.status.value}, "
              f"стадия {game.stage.value}")
        print("Записано.")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
