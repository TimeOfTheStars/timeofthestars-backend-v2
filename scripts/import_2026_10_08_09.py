# -*- coding: utf-8 -*-
"""Протоколы матчей 08.10.2026 и 09.10.2026.

Игра 24 (Дебют): Вымпел-V (A) — Время звезд (B). В основное время 3:3,
победа Вымпела по буллитам. В базе сейчас стоит 4:3 — исправляем на 3:3
плюс bullet_win_team_id, иначе Время звёзд теряет очко за ничью, а сумма
голов в таймлайне не сходится со счётом.

Игра 27 (Звезда Отечества): ЯВВУ ПВО (A) — Торпедо (B), 6:13.

Решения заказчика:
  * счёт 08.10 — 3:3 с победой Вымпела по буллитам;
  * восьми игрокам ЯВВУ убираем отчества: в базе принято «Фамилия Имя»;
  * «Дмитриев Артем» №14 — это Дмитричев Артём;
  * удаление Торпедо на «0» (2:50) не вносится, как 06.09 у Арктика;
  * командный штраф «К» у Времени звёзд (6:41) не вносится, как раньше.

    PYTHONPATH=/app python /tmp/import_oct.py --dry-run
    PYTHONPATH=/app python /tmp/import_oct.py --apply
"""

import asyncio
import sys

from sqlalchemy import select

from app.db.session import async_session_maker
from app.models import CompetitionPlayer, Player
from app.models.enums import GameEventType
from app.schemas.game import GameEventIn, PlayerStatLine, ProtocolRequest
from app.schemas.player import PlayerUpdate
from app.services import game_service, player_service

G, SO, P, GC = (GameEventType.goal, GameEventType.shootout_goal,
                GameEventType.penalty, GameEventType.goalie_change)

VYMPEL, ZVEZD = 3, 8          # Дебют
YAVVU, TORPEDO = 7, 5         # Звезда Отечества

# Отчества убираем: в базе принят вид «Фамилия Имя»
DROP_PATRONYMIC = {
    "Ильин Егор Владимирович": "Ильин Егор",
    "Сидоров Григорий Алексеевич": "Сидоров Григорий",
    "Муторов Семен Михайлович": "Муторов Семен",
    "Жанабергенов Темирлан Александрович": "Жанабергенов Темирлан",
    "Андреев Иван Александрович": "Андреев Иван",
    "Сковорода Владислав Антонович": "Сковорода Владислав",
    "Лопатин Андрей Витальевич": "Лопатин Андрей",
    "Козлов Тимофей Михайлович": "Козлов Тимофей",
}

ALIAS = {"Дмитриев Артем": "Дмитричев Артём"}

# ключ — номер из протокола; «б/н» у Вымпела получает служебный ключ 0
LINEUPS = {
    (24, VYMPEL): {
        6: "Мольков Денис", 89: "Лашов Константин", 0: "Кибальский Виктор",
        9: "Тепляков Александр", 17: "Сомов Илья", 21: "Чесноков Андрей",
        24: "Рабинович Виктор", 33: "Богунов Кирилл", 38: "Идиатуллин Александр",
        44: "Барашков Данила", 48: "Шилов Сергей", 49: "Белянцев Тимур",
        58: "Кошелев Ярослав", 59: "Барабанов Сергей", 76: "Михеев Алексей",
        80: "Галанин Александр", 88: "Щетинин Дмитрий", 96: "Коркишко Роман",
        98: "Майер Артем",
    },
    (24, ZVEZD): {
        90: "Едемский Вадим", 3: "Веселов Артур", 4: "Лосев Игорь", 6: "Горев Артем",
        8: "Орлов Максим", 9: "Гаврилычев Максим", 11: "Балов Артем",
        12: "Торусин Александр", 13: "Шарамонов Евгений", 24: "Наумцев Антон",
        34: "Подручный Алексей", 71: "Корякин Андрей", 72: "Светашов Максим",
        76: "Казунин Дмитрий", 77: "Никулин Арсений", 91: "Нищев Артем",
        92: "Фомичев Иван",
    },
    (27, YAVVU): {
        1: "Ильин Егор", 2: "Котко Матвей", 20: "Сидоров Григорий", 16: "Сухов Кирилл",
        5: "Бардин Даниил", 10: "Муторов Семен", 8: "Жанабергенов Темирлан",
        9: "Андреев Иван", 6: "Сковорода Владислав", 11: "Кузнецов Савелий",
        12: "Лобов Матвей", 4: "Белоусов Анатолий", 3: "Лопатин Андрей",
        14: "Хорохорин Александр", 15: "Балакин Александр", 19: "Козлов Тимофей",
        17: "Свешников Вячеслав", 13: "Кокарев Александр", 7: "Смирнов Даниил",
        18: "Иванов Иван",
    },
    (27, TORPEDO): {
        32: "Пеньков Никита", 18: "Камушков Клим", 92: "Гусаров Александр",
        8: "Медведев Георгий", 19: "Пятаков Алексей", 14: "Дмитриев Артем",
        12: "Таганчиков Сергей", 79: "Марков Андрей", 27: "Иванов Андрей",
        54: "Зазнобин Егор", 89: "Иванов Тихон", 97: "Железняков Мирослав",
        96: "Олин Лев",
    },
}

GAMES = {
    24: dict(
        comp=3, teams=(VYMPEL, ZVEZD), score={VYMPEL: 3, ZVEZD: 3}, bullet_win=VYMPEL,
        # Лашов 0:00-52:00 и 56:30-60:00 (55:30 -> 55), Мольков 52:00-56:30 (4:30 -> 4).
        # Голы ВЗ: 23:00 при Лашове; 55:15 и 56:30 при Молькове.
        goalies={VYMPEL: {89: (1, 55), 6: (2, 4)}, ZVEZD: {90: (3, 60)}},
        expect_periods={VYMPEL: [1, 2, 0], ZVEZD: [0, 1, 2]},
        expect_pim={VYMPEL: 8, ZVEZD: 6},   # у ВЗ в бумаге 8, минус командный «К»
        events=[
            (0, 0, GC, VYMPEL, 89, None, None, None),
            (0, 0, GC, ZVEZD, 90, None, None, None),
            (1, 12, P, ZVEZD, 13, None, None, 2),
            (3, 53, P, VYMPEL, 76, None, None, 2),
            (5, 47, P, ZVEZD, 71, None, None, 2),
            # 6:41 — командный штраф «К» Времени звёзд, не вносится
            (8, 5, P, VYMPEL, 76, None, None, 2),
            (14, 50, G, VYMPEL, 33, 0, 88, None),
            (23, 0, G, ZVEZD, 12, None, None, None),
            (25, 45, G, VYMPEL, 0, None, None, None),
            (26, 50, P, VYMPEL, 17, None, None, 2),
            (33, 19, P, VYMPEL, 76, None, None, 2),
            (33, 19, P, ZVEZD, 9, None, None, 2),
            (34, 55, G, VYMPEL, 0, 33, 48, None),
            (52, 0, GC, VYMPEL, 6, None, None, None),
            (55, 15, G, ZVEZD, 3, None, None, None),
            (56, 30, G, ZVEZD, 92, None, None, None),
            (56, 30, GC, VYMPEL, 89, None, None, None),
            (60, 0, SO, VYMPEL, 38, None, None, None),   # победный буллит
        ],
    ),
    27: dict(
        comp=4, teams=(YAVVU, TORPEDO), score={YAVVU: 6, TORPEDO: 13}, bullet_win=None,
        # у ЯВВУ: №1 Ильин 0:00-29:37 и 51:46-60:00, №18 Иванов 29:37-51:46
        # Ильин 0:00-29:37 и 51:46-60:00 (37:51 -> 37), Иванов между ними (22:09 -> 22);
        # пропущенные разнесены по времени на льду
        goalies={YAVVU: {1: (6, 37), 18: (7, 22)}, TORPEDO: {32: (6, 60)}},
        # счёт по периодам в этой бумаге не заполнен — посчитан по событиям
        expect_periods={YAVVU: [1, 2, 3], TORPEDO: [1, 7, 5]},
        expect_pim={YAVVU: 2, TORPEDO: 2},   # у Торпедо в бумаге 4, минус штраф на «0»
        events=[
            (0, 0, GC, YAVVU, 1, None, None, None),
            (0, 0, GC, TORPEDO, 32, None, None, None),
            # 2:50 — удаление Торпедо на «0», не вносится
            (9, 14, G, YAVVU, 14, 5, 11, None),
            (17, 34, G, TORPEDO, 19, 54, None, None),
            (22, 3, G, YAVVU, 7, 17, None, None),
            (22, 53, G, YAVVU, 19, None, None, None),
            (24, 14, G, TORPEDO, 54, 27, 19, None),
            (26, 10, P, YAVVU, 5, None, None, 2),
            (26, 24, G, TORPEDO, 14, 79, 19, None),      # в большинстве
            (29, 20, P, TORPEDO, 96, None, None, 2),
            (29, 37, G, TORPEDO, 97, None, None, None),
            (29, 37, GC, YAVVU, 18, None, None, None),
            (33, 13, G, TORPEDO, 14, None, None, None),
            (34, 9, G, TORPEDO, 12, None, None, None),
            (35, 54, G, TORPEDO, 18, 89, 97, None),
            (38, 8, G, TORPEDO, 79, 19, 54, None),
            (42, 0, G, TORPEDO, 18, 79, 89, None),
            (49, 4, G, TORPEDO, 18, 92, 19, None),
            (51, 46, G, TORPEDO, 19, 54, 27, None),
            (51, 46, GC, YAVVU, 1, None, None, None),
            (53, 25, G, TORPEDO, 14, 8, None, None),
            (54, 4, G, YAVVU, 7, 5, None, None),
            (56, 4, G, TORPEDO, 97, 18, None, None),
            (57, 17, G, YAVVU, 15, 11, None, None),
            (58, 28, G, YAVVU, 15, 11, None, None),
        ],
    ),
}


def period(sec: int) -> int:
    return 1 if sec <= 0 else min((sec - 1) // 1200 + 1, 3)


async def fix_names(db, apply: bool):
    print("=== отчества в именах ===")
    for old, new in DROP_PATRONYMIC.items():
        player = (await db.execute(select(Player).where(Player.full_name == old))).scalars().first()
        if player is None:
            exists = (await db.execute(select(Player).where(Player.full_name == new))).scalars().all()
            print(f"  {old} — уже нет; «{new}» в базе: {len(exists)}")
            continue
        clash = (await db.execute(select(Player).where(Player.full_name == new))).scalars().all()
        if clash:
            raise SystemExit(f"«{new}» уже занято (id {[p.id for p in clash]}) — нужен разбор")
        print(f"  id={player.id:<4} «{old}» -> «{new}»")
        if apply:
            await player_service.update(db, player, PlayerUpdate(full_name=new))


# обратный словарь: в dry-run отчества ещё не убраны, ищем по старому имени
PATRONYMIC_BACK = {new: old for old, new in DROP_PATRONYMIC.items()}


async def resolve(db, comp_id, team_id, key, apply: bool):
    rows = (await db.execute(
        select(Player)
        .join(CompetitionPlayer, CompetitionPlayer.player_id == Player.id)
        .where(CompetitionPlayer.competition_id == comp_id,
               CompetitionPlayer.team_id == team_id)
    )).scalars().all()
    by_name = {p.full_name: p for p in rows}
    out = {}
    for number, name in LINEUPS[key].items():
        db_name = ALIAS.get(name, name)
        player = by_name.get(db_name)
        if player is None and not apply and db_name in PATRONYMIC_BACK:
            player = by_name.get(PATRONYMIC_BACK[db_name])
        if player is None:
            raise SystemExit(f"НЕ НАЙДЕН в заявке {team_id}: {name} (искали «{db_name}»)")
        out[number] = player
    return out


async def process(db, game_id, spec, apply: bool):
    game = await game_service.get_with_protocol(db, game_id)
    team_a, team_b = spec["teams"]
    if (game.team_a_id, game.team_b_id) != (team_a, team_b):
        raise SystemExit(f"игра {game_id}: в базе {game.team_a_id} vs {game.team_b_id}")
    print(f"\n=== игра {game_id}: {game.date} {game.time}, сейчас "
          f"{game.score_team_a}:{game.score_team_b}, строк {len(game.player_stats)}, "
          f"событий {len(game.events)} ===")

    rosters = {tid: await resolve(db, spec["comp"], tid, (game_id, tid), apply)
               for tid in (team_a, team_b)}

    lines = []
    for team_id in (team_a, team_b):
        goalies = spec["goalies"].get(team_id, {})
        for number, _name in LINEUPS[(game_id, team_id)].items():
            extra = {}
            if number in goalies:
                against, minutes = goalies[number]
                extra = dict(is_goalie=True, goals_against=against, minutes_played=minutes)
            lines.append(PlayerStatLine(
                player_id=rosters[team_id][number].id, team_id=team_id, **extra))

    events = []
    for mm, ss, etype, team_id, num, a1, a2, pim in spec["events"]:
        mapping = rosters[team_id]
        for n in (num, a1, a2):
            if n is not None and n not in mapping:
                raise SystemExit(f"игра {game_id}: нет №{n} в составе команды {team_id}")
        events.append(GameEventIn(
            type=etype, team_id=team_id, time_seconds=mm * 60 + ss,
            player_id=mapping[num].id,
            assist1_player_id=mapping[a1].id if a1 is not None else None,
            assist2_player_id=mapping[a2].id if a2 is not None else None,
            penalty_minutes=pim,
        ))

    goals = {team_a: 0, team_b: 0}
    per = {team_a: [0, 0, 0], team_b: [0, 0, 0]}
    pim = {team_a: 0, team_b: 0}
    shootout = {team_a: 0, team_b: 0}
    for ev in events:
        if ev.type is GameEventType.goal:
            goals[ev.team_id] += 1
            per[ev.team_id][period(ev.time_seconds) - 1] += 1
        elif ev.type is GameEventType.shootout_goal:
            shootout[ev.team_id] += 1
        elif ev.type is GameEventType.penalty:
            pim[ev.team_id] += ev.penalty_minutes

    print(f"  голов {goals[team_a]}:{goals[team_b]}, ставим счёт "
          f"{spec['score'][team_a]}:{spec['score'][team_b]}"
          + (f", буллиты команде {spec['bullet_win']}" if spec["bullet_win"] else ""))
    print(f"  периоды {team_a}: {per[team_a]} (бумага {spec['expect_periods'][team_a]}), "
          f"{team_b}: {per[team_b]} (бумага {spec['expect_periods'][team_b]})")
    print(f"  штраф {team_a}: {pim[team_a]}, {team_b}: {pim[team_b]} "
          f"(ожидали {spec['expect_pim'][team_a]}:{spec['expect_pim'][team_b]})")
    print(f"  строк участия {len(lines)}, событий {len(events)}, буллит-голов "
          f"{shootout[team_a]}:{shootout[team_b]}")

    assert goals[team_a] == spec["score"][team_a] and goals[team_b] == spec["score"][team_b], "счёт"
    assert per[team_a] == spec["expect_periods"][team_a], "периоды хозяев"
    assert per[team_b] == spec["expect_periods"][team_b], "периоды гостей"
    assert pim == spec["expect_pim"], "штраф"

    if not apply:
        return len(lines), len(events)

    await game_service.save_protocol(db, game, ProtocolRequest(
        score_team_a=spec["score"][team_a], score_team_b=spec["score"][team_b],
        bullet_win_team_id=spec["bullet_win"],
        stat_lines=lines, events=events, team_stats=None,
    ))
    print("  записано")
    return len(lines), len(events)


async def main(apply: bool):
    expected = {}
    async with async_session_maker() as db:
        await fix_names(db, apply)
        if apply:
            await db.flush()
        for game_id, spec in GAMES.items():
            expected[game_id] = await process(db, game_id, spec, apply)
        if apply:
            await db.commit()
        else:
            print("\n--- dry-run, ничего не записано ---")
            return

    async with async_session_maker() as db:
        print()
        for game_id, (n_lines, n_events) in expected.items():
            game = await game_service.get_with_protocol(db, game_id)
            assert len(game.player_stats) == n_lines, f"игра {game_id}: строки"
            assert len(game.events) == n_events, f"игра {game_id}: события"
            print(f"  игра {game_id}: {game.score_team_a}:{game.score_team_b}, "
                  f"буллиты {game.bullet_win_team_id}, строк {len(game.player_stats)}, "
                  f"событий {len(game.events)}, статус {game.status.value}")
        print("Записано.")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
