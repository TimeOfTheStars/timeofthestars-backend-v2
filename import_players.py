#!/usr/bin/env python
"""Импорт игроков из JSON-файла.

Поля `id` и `photo_url` игнорируются (photo_url ставится в NULL).
Идемпотентно: игрок с такими же ФИО и датой рождения повторно не создаётся.

Использование:
    python import_players.py [путь_к_json]      # по умолчанию players_import.json
    python import_players.py -                  # читать JSON из stdin
"""
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.db.session import async_session_maker
from app.models import Player


def parse_date(v) -> dt.date | None:
    if not v:
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def clean(v) -> str | None:
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def canon_position(v) -> str | None:
    """Приводит позицию к одному из 3 канонических значений (или None)."""
    s = (v or "").strip().lower()
    if s.startswith("врат"):
        return "вратарь"
    if s.startswith("защит"):
        return "защитник"
    if s.startswith("напад"):
        return "нападающий"
    return None


async def main(raw: str) -> None:
    data = json.loads(raw)
    if not isinstance(data, list):
        raise SystemExit("Ожидался JSON-массив игроков")

    added = skipped = bad = 0
    async with async_session_maker() as db:
        for rec in data:
            name = clean(rec.get("full_name"))
            if not name:
                bad += 1
                continue
            bd = parse_date(rec.get("birth_date"))
            exists = (
                await db.execute(
                    select(Player.id).where(Player.full_name == name, Player.birth_date == bd)
                )
            ).first()
            if exists:
                skipped += 1
                continue
            db.add(
                Player(
                    full_name=name,
                    birth_date=bd,
                    position=canon_position(rec.get("position")),
                    grip=clean(rec.get("grip")),
                    photo_url=None,  # игнорируем по требованию
                )
            )
            added += 1
        await db.commit()
    print(f"Добавлено: {added} · пропущено (дубликаты): {skipped} · без имени: {bad}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "players_import.json"
    if arg == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(arg).read_text(encoding="utf-8")
    asyncio.run(main(raw))
