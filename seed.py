#!/usr/bin/env python
"""Наполнение БД демонстрационными данными.

    python seed.py
Идемпотентность не гарантируется — запускать на чистой БД.
"""
import asyncio
import datetime as dt

from app.db.session import async_session_maker
from app.models.enums import CompetitionType, GameEventType, GameStage, UserRole
from app.schemas.auth import UserCreate
from app.schemas.competition import CompetitionCreate
from app.schemas.game import (
    GameCreate,
    GameEventIn,
    PlayerStatLine,
    ProtocolRequest,
)
from app.schemas.player import PlayerCreate
from app.schemas.team import TeamCreate
from app.services import (
    competition_service,
    game_service,
    player_service,
    team_service,
    user_service,
)

TEAMS = ["Сокол", "Молния", "Барс", "Комета"]
PLAYERS = [
    ("Иван Петров", "нападающий"),
    ("Сергей Смирнов", "защитник"),
    ("Алексей Кузнецов", "вратарь"),
    ("Дмитрий Попов", "нападающий"),
    ("Николай Васильев", "защитник"),
    ("Андрей Морозов", "вратарь"),
    ("Павел Новиков", "нападающий"),
    ("Михаил Фёдоров", "защитник"),
]


async def main() -> None:
    async with async_session_maker() as db:
        # Админ
        if not await user_service.get_by_username(db, "admin"):
            await user_service.create(
                db, UserCreate(username="admin", password="admin", role=UserRole.admin)
            )

        # Команды и игроки
        teams = [await team_service.create(db, TeamCreate(name=n, city="Москва")) for n in TEAMS]
        players = [
            await player_service.create(db, PlayerCreate(full_name=fn, position=pos))
            for fn, pos in PLAYERS
        ]

        # Соревнование
        comp = await competition_service.create(
            db,
            CompetitionCreate(
                type=CompetitionType.championship,
                name="Открытый чемпионат 2026",
                start_date=dt.date(2026, 1, 10),
                location="Москва",
                show_best_players=True,
            ),
        )

        # Заявка: по 2 игрока в первые 2 команды
        await competition_service.add_player(db, comp.id, teams[0].id, players[0].id, 9, True)
        await competition_service.add_player(db, comp.id, teams[0].id, players[1].id, 4, True)
        await competition_service.add_player(db, comp.id, teams[0].id, players[2].id, 30, True)
        await competition_service.add_player(db, comp.id, teams[1].id, players[3].id, 11, True)
        await competition_service.add_player(db, comp.id, teams[1].id, players[4].id, 7, False)
        await competition_service.add_player(db, comp.id, teams[1].id, players[5].id, 1, True)

        # Матч с протоколом
        game = await game_service.create(
            db,
            GameCreate(
                competition_id=comp.id,
                team_a_id=teams[0].id,
                team_b_id=teams[1].id,
                date=dt.date(2026, 1, 12),
                time=dt.time(19, 0),
                location="Арена",
                stage=GameStage.matches,
            ),
        )
        await game_service.save_protocol(
            db,
            game,
            ProtocolRequest(
                score_team_a=3,
                score_team_b=2,
                stat_lines=[
                    PlayerStatLine(player_id=players[0].id, team_id=teams[0].id),
                    PlayerStatLine(player_id=players[1].id, team_id=teams[0].id),
                    PlayerStatLine(
                        player_id=players[2].id, team_id=teams[0].id,
                        is_goalie=True, goals_against=2, saves=18, minutes_played=60,
                    ),
                    PlayerStatLine(player_id=players[3].id, team_id=teams[1].id),
                    PlayerStatLine(
                        player_id=players[5].id, team_id=teams[1].id,
                        is_goalie=True, goals_against=3, saves=21, minutes_played=60,
                    ),
                ],
                # Голы и передачи считаются из таймлайна
                events=[
                    GameEventIn(
                        type=GameEventType.goalie_change, team_id=teams[0].id,
                        time_seconds=0, player_id=players[2].id,
                    ),
                    GameEventIn(
                        type=GameEventType.goal, team_id=teams[0].id,
                        time_seconds=305, player_id=players[0].id,
                        assist1_player_id=players[1].id, video_seconds=2705,
                    ),
                    GameEventIn(
                        type=GameEventType.goal, team_id=teams[1].id,
                        time_seconds=980, player_id=players[3].id,
                    ),
                    GameEventIn(
                        type=GameEventType.penalty, team_id=teams[0].id,
                        time_seconds=1510, player_id=players[1].id, penalty_minutes=2,
                    ),
                    GameEventIn(
                        type=GameEventType.goal, team_id=teams[0].id,
                        time_seconds=2210, player_id=players[0].id,
                    ),
                    GameEventIn(
                        type=GameEventType.goal, team_id=teams[1].id,
                        time_seconds=2890, player_id=players[3].id,
                    ),
                    GameEventIn(
                        type=GameEventType.goal, team_id=teams[0].id,
                        time_seconds=3400, player_id=players[1].id,
                        assist1_player_id=players[0].id,
                    ),
                ],
            ),
        )

        await db.commit()
        print("Готово: демо-данные созданы. Логин admin / admin.")


if __name__ == "__main__":
    asyncio.run(main())
