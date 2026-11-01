# -*- coding: utf-8 -*-
"""Дозаявка в чемпионат «Звезда Отечества» (Любитель), соревнование 5.

Источники:
  * «Кристалл» — две записки заказчика от 01.11.2026 (три игрока);
  * «Армада» — заявочный лист сезона 2026-2027,
    ~/Downloads/ZAYaVOChNYI_774_LIST_KOMANDY_ARMADA_VREMYa_ZVEZD_2026-2027.docx
    (34 строки, одна пустая).

Решения заказчика от 01.11.2026:
  * заявку «Армады» **заменяем целиком** по листу: 26 человек, которых в листе
    нет, из заявки удаляются. Пятеро из них уже отыграли по матчу (Большаков,
    Егурнов, Мальцев, Махмудов, Яковлев Ярослав) — строки их протоколов
    остаются, из заявки они уходят;
  * Едемский Вадим (id 604) из листа «Армады» **пропускается**: он заявлен за
    «Время звезд» под №1 и отыграл за них 28.10. Один это человек или
    однофамилец — решаем отдельно. Из-за этого в заявке 33 человека, не 34;
  * «Корючков Алексей» (id 687) — опечатка, правим на «Крючков Алексей»
    и меняем его номер в заявке с 50 на 91 (как в листе);
  * расхождения базы и листа правим по листу: Шильников Родион (id 459)
    защитник -> нападающий, Тихонов Ярослав (id 2) вратарь -> нападающий,
    Орлов Антон (id 688) 12.12.1992 -> 13.12.1992.

Рост, вес и место рождения из листа схема не хранит — не записываются.
Отчества не записываются: в базе имена в формате «Фамилия Имя».

Запуск на сервере (сначала всегда dry-run):

    ssh tots 'cd /srv/tots/repo && git pull'
    ssh tots 'sudo /usr/local/bin/tots-backup.sh'
    ssh tots 'cd /srv/tots/repo && docker compose exec -T api \
        python scripts/dozayavka_2026_11_01.py'
    ssh tots 'cd /srv/tots/repo && docker compose exec -T api \
        python scripts/dozayavka_2026_11_01.py --apply'
"""

import asyncio
import datetime as dt
import sys

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import CompetitionPlayer, Player
from app.models.enums import PlayerPosition

COMP = 5            # Звезда Отечества (Любитель)
ARMADA = 10
KRISTALL = 17

F, D, G = PlayerPosition.forward, PlayerPosition.defender, PlayerPosition.goalie


def d(s: str) -> dt.date:
    """Дата из листа: ДД.ММ.ГГГГ."""
    return dt.datetime.strptime(s, "%d.%m.%Y").date()


# --- правки карточек: id -> поле -> новое значение -------------------------
# Каждая правка сопровождается ожидаемым текущим значением: если в базе не оно,
# скрипт останавливается, а не пишет поверх чего-то незнакомого.
FIXES = [
    # (id, ожидаемое имя, поле, было, стало)
    (687, "Корючков Алексей", "full_name", "Корючков Алексей", "Крючков Алексей"),
    (688, "Орлов Антон", "birth_date", dt.date(1992, 12, 12), dt.date(1992, 12, 13)),
    (2, "Тихонов Ярослав", "position", G, F),
    (459, "Шильников Родион", "position", D, F),
    # пустые поля заполняем по листу
    (543, "Барышев Михаил", "birth_date", None, d("07.02.2003")),
    (543, "Барышев Михаил", "grip", None, "правый"),
]

# --- новые карточки: имя -> (дата, амплуа, хват) ---------------------------
NEW_PLAYERS = {
    "Белосевич Авель":      (d("27.10.1992"), F, "левый"),
    "Бойцов Андрей":        (d("14.09.2003"), D, "левый"),
    "Воскресенский Андрей": (d("11.05.1989"), G, "левый"),
    "Крючков Александр":    (d("06.10.2001"), F, "правый"),
    "Пологих Олег":         (d("26.06.2008"), F, None),
}

# --- целевые заявки -------------------------------------------------------
# id | имя для сверки (None — новая карточка, ищется по имени) | номер
ARMADA_ROSTER = [
    (497, "Абрамов Артём",        69),
    (665, "Барышев Андрей",        9),
    (543, "Барышев Михаил",       25),
    (None, "Белосевич Авель",     92),
    (666, "Белосевич Вениамин",   19),
    (691, "Быков Кирилл",         18),
    (349, "Бычков Николай",       31),
    (668, "Воробьев Александр",    7),
    (669, "Воробьев Игорь",       13),
    (670, "Гнездов Алексей",       4),
    (671, "Голубев Александр",    17),
    (268, "Забойкин Евгений",     71),
    (672, "Коровкин Дмитрий",     72),
    (673, "Лубнин Даниил",        98),
    (674, "Масляков Александр",   42),
    (675, "Масляков Николай",     79),
    (688, "Орлов Антон",           8),
    (678, "Самойлов Дмитрий",     47),
    (679, "Тарканий Денис",       11),
    (2,   "Тихонов Ярослав",      33),
    (680, "Трубачев Станислав",   55),
    (251, "Трусов Александр",     88),
    (692, "Тюлин Лев",            89),
    (681, "Тютянов Дмитрий",      20),
    (682, "Федюкин Кирилл",       51),
    (258, "Фурманец Виталий",     73),
    (257, "Фурманец Сергей",      22),
    (685, "Шаров Фёдор",           1),
    (None, "Бойцов Андрей",       46),
    (254, "Филимонов Дмитрий",    14),
    # №31 листа — Едемский Вадим В №41 — пропущен по решению заказчика
    (None, "Воскресенский Андрей", 37),
    (687, "Крючков Алексей",      91),   # он же «Корючков», см. FIXES
    (None, "Крючков Александр",   90),
]

# «Кристалл» — только дозаявка, из заявки никого не убираем
KRISTALL_ADD = [
    (459,  "Шильников Родион", 10),
    (None, "Пологих Олег",      7),
    (488,  "Голов Егор",       86),
]

# Старые написания, которые правит FIXES: до --apply в базе ещё они, и сверка
# имени по целевой заявке должна их принимать.
ALIASES = {687: {"Корючков Алексей"}}

# Эти игроки уже отыграли за «Армаду» — их удаление из заявки заказчик
# подтвердил отдельно. Список нужен, чтобы заметить, если отыгравших стало
# больше, чем было на сверке 01.11.
PLAYED_BUT_DROPPED = {667, 252, 262, 676, 686}


async def fetch_players(db, ids):
    if not ids:
        return {}
    rows = (await db.execute(select(Player).where(Player.id.in_(ids)))).scalars().all()
    return {p.id: p for p in rows}


async def find_by_name(db, name):
    return (await db.execute(select(Player).where(Player.full_name == name))).scalars().all()


async def apply_fixes(db, apply):
    ids = sorted({f[0] for f in FIXES})
    players = await fetch_players(db, ids)
    print("\n=== правки карточек ===")
    for pid, expect_name, field, was, now in FIXES:
        p = players.get(pid)
        if p is None:
            raise SystemExit(f"игрок id {pid} не найден")
        # имя сверяем по тому, что ожидали увидеть ДО правки имени
        cur = getattr(p, field)
        if cur == now:
            print(f"  id {pid} {p.full_name}: {field} уже {now} — пропуск")
            continue
        if cur != was:
            raise SystemExit(
                f"id {pid} {p.full_name}: {field} в базе {cur!r}, ждали {was!r} — разбор"
            )
        print(f"  id {pid} {expect_name}: {field} {cur!r} -> {now!r}")
        if apply:
            setattr(p, field, now)
    if apply:
        await db.flush()


async def ensure_new_players(db, apply):
    print("\n=== новые карточки ===")
    created = {}
    for name, (birth, pos, grip) in NEW_PLAYERS.items():
        hits = await find_by_name(db, name)
        if len(hits) > 1:
            raise SystemExit(f"«{name}» в базе {len(hits)} раз — разбор")
        if hits:
            p = hits[0]
            print(f"  уже есть: id {p.id} {name} | {p.birth_date} | {p.position} | {p.grip}")
            created[name] = p
            continue
        print(f"  создать: {name} | {birth} | {pos.value} | {grip}")
        if apply:
            p = Player(full_name=name, birth_date=birth, position=pos, grip=grip)
            db.add(p)
            created[name] = p
    if apply:
        await db.flush()
        for name, p in created.items():
            print(f"    {name} -> id {p.id}")
    return created


async def current_roster(db, team_id):
    rows = (
        await db.execute(
            select(CompetitionPlayer)
            .options(selectinload(CompetitionPlayer.player))
            .where(
                CompetitionPlayer.competition_id == COMP,
                CompetitionPlayer.team_id == team_id,
            )
        )
    ).scalars().all()
    return {r.player_id: r for r in rows}


async def resolve(db, target, new_players, apply):
    """Список (player_id, имя, номер) по целевой заявке."""
    out = []
    for pid, name, number in target:
        if pid is None:
            p = new_players.get(name)
            if p is None:
                if not apply:
                    out.append((None, name, number))     # в dry-run её ещё нет
                    continue
                raise SystemExit(f"новая карточка «{name}» не создана")
            pid = p.id
        else:
            got = await fetch_players(db, [pid])
            p = got.get(pid)
            if p is None:
                raise SystemExit(f"игрок id {pid} ({name}) не найден")
            if p.full_name != name and p.full_name not in ALIASES.get(pid, ()):
                raise SystemExit(f"id {pid}: в базе «{p.full_name}», ждали «{name}»")
        out.append((pid, name, number))
    return out


def check_numbers(label, rows):
    seen = {}
    for pid, name, number in rows:
        if number is None:
            continue
        seen.setdefault(number, []).append(name)
    dup = {n: names for n, names in seen.items() if len(names) > 1}
    if dup:
        for n, names in sorted(dup.items()):
            print(f"  ВНИМАНИЕ {label}: №{n} у {', '.join(names)}")


async def sync_armada(db, new_players, apply):
    print("\n=== Армада (команда 10): заявка заменяется по листу ===")
    target = await resolve(db, ARMADA_ROSTER, new_players, apply)
    check_numbers("Армада", target)
    cur = await current_roster(db, ARMADA)
    target_ids = {pid for pid, _, _ in target if pid is not None}

    print(f"  в базе {len(cur)} человек, в листе {len(ARMADA_ROSTER)}")

    print("  -- добавить --")
    added = 0
    for pid, name, number in target:
        if pid is None:
            print(f"     (dry-run) {name} №{number} — карточки ещё нет")
            added += 1
            continue
        if pid in cur:
            continue
        print(f"     + id {pid} {name} №{number}")
        added += 1
        if apply:
            db.add(
                CompetitionPlayer(
                    competition_id=COMP, team_id=ARMADA, player_id=pid, number=number
                )
            )
    if not added:
        print("     нечего")

    print("  -- поменять номер --")
    renum = 0
    for pid, name, number in target:
        row = cur.get(pid) if pid is not None else None
        if row is None or row.number == number:
            continue
        print(f"     ~ id {pid} {name}: №{row.number} -> №{number}")
        renum += 1
        if apply:
            row.number = number
    if not renum:
        print("     нечего")

    print("  -- удалить из заявки --")
    to_drop = [r for pid, r in sorted(cur.items()) if pid not in target_ids]
    played_now = {r.player_id for r in to_drop if r.player_id in PLAYED_BUT_DROPPED}
    for r in sorted(to_drop, key=lambda r: r.player.full_name):
        mark = " (отыграл матч)" if r.player_id in PLAYED_BUT_DROPPED else ""
        print(f"     - id {r.player_id} #{r.number} {r.player.full_name}{mark}")
        if apply:
            await db.delete(r)
    print(f"     всего {len(to_drop)}, из них отыгравших {len(played_now)}")
    if played_now != PLAYED_BUT_DROPPED:
        raise SystemExit(
            "список отыгравших разошёлся со сверкой 01.11: "
            f"{sorted(played_now)} вместо {sorted(PLAYED_BUT_DROPPED)} — разбор"
        )
    return len(target_ids)


async def add_kristall(db, new_players, apply):
    print("\n=== Кристалл (команда 17): только дозаявка ===")
    target = await resolve(db, KRISTALL_ADD, new_players, apply)
    cur = await current_roster(db, KRISTALL)
    busy = {r.number: r.player.full_name for r in cur.values() if r.number is not None}
    print(f"  в заявке {len(cur)} человек")
    for pid, name, number in target:
        if number in busy:
            print(f"     ВНИМАНИЕ: №{number} уже у {busy[number]}")
        if pid is None:
            print(f"     (dry-run) {name} №{number} — карточки ещё нет")
            continue
        if pid in cur:
            print(f"     уже в заявке: id {pid} {name} №{cur[pid].number}")
            continue
        print(f"     + id {pid} {name} №{number}")
        if apply:
            db.add(
                CompetitionPlayer(
                    competition_id=COMP, team_id=KRISTALL, player_id=pid, number=number
                )
            )
    return len(cur) + sum(1 for pid, _, _ in target if pid is None or pid not in cur)


async def main(apply: bool) -> None:
    from app.db.session import async_session_maker

    async with async_session_maker() as db:
        await apply_fixes(db, apply)
        new_players = await ensure_new_players(db, apply)
        n_armada = await sync_armada(db, new_players, apply)
        n_kristall = await add_kristall(db, new_players, apply)
        if not apply:
            print("\n--- dry-run, ничего не записано ---")
            print("    (новых карточек ещё нет, поэтому часть строк показана как «dry-run»)")
            return
        await db.commit()
        print("\n  записано")

    async with async_session_maker() as db:
        for team_id, name, expect in ((ARMADA, "Армада", n_armada), (KRISTALL, "Кристалл", None)):
            rows = await current_roster(db, team_id)
            print(f"\n=== {name}: в заявке {len(rows)} ===")
            for r in sorted(rows.values(), key=lambda r: r.player.full_name):
                p = r.player
                print(
                    f"  {p.id:>5} | #{r.number if r.number is not None else '-':<4} | "
                    f"{p.full_name:<28} | {p.birth_date} | {p.position} | {p.grip}"
                )
            if expect is not None and len(rows) != expect:
                raise SystemExit(f"{name}: в заявке {len(rows)}, ждали {expect}")
    print("\nГотово.")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
