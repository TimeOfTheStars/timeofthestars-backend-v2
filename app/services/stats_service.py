from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Competition,
    CompetitionTeam,
    Game,
    GamePlayerStat,
    Player,
    Team,
)
from app.models.enums import GameStage
from app.schemas.stats import (
    BestPlayer,
    PlayerCompetitionStat,
    PlayerStatsBreakdown,
    PlayerStatTotals,
    PlayerTeamStat,
    StandingRow,
)
from app.schemas.player import PlayerRead
from app.schemas.team import TeamRead


async def compute_standings(db: AsyncSession, competition_id: int) -> list[StandingRow]:
    """Турнирная таблица, вычисляется из сыгранных матчей регулярки."""
    teams_res = await db.execute(
        select(Team)
        .join(CompetitionTeam, CompetitionTeam.team_id == Team.id)
        .where(CompetitionTeam.competition_id == competition_id)
    )
    teams = {t.id: t for t in teams_res.scalars().all()}

    rows: dict[int, StandingRow] = {
        tid: StandingRow(team=TeamRead.model_validate(team)) for tid, team in teams.items()
    }

    games_res = await db.execute(
        select(Game).where(
            Game.competition_id == competition_id,
            Game.stage == GameStage.matches,
            Game.score_team_a.isnot(None),
            Game.score_team_b.isnot(None),
        )
    )
    for game in games_res.scalars().all():
        a, b = game.team_a_id, game.team_b_id
        sa, sb = game.score_team_a, game.score_team_b
        for tid, gf, ga in ((a, sa, sb), (b, sb, sa)):
            row = rows.get(tid)
            if row is None:
                continue
            row.games += 1
            row.goals_scored += gf
            row.goals_conceded += ga
            if gf > ga:
                row.wins += 1
            elif gf < ga:
                row.losses += 1
            else:
                row.draws += 1
                if game.bullet_win_team_id == tid:
                    row.extra_points += 1

    for row in rows.values():
        row.points = row.wins * 2 + row.draws * 1 + row.extra_points * 1

    return sorted(
        rows.values(),
        key=lambda r: (r.points, r.goals_scored - r.goals_conceded, r.goals_scored),
        reverse=True,
    )


def _totals_from_row(row) -> PlayerStatTotals:
    return PlayerStatTotals(
        games=row.games or 0,
        goals=row.goals or 0,
        assists=row.assists or 0,
        points=(row.goals or 0) + (row.assists or 0),
        penalties=row.penalties or 0,
        goals_against=row.goals_against or 0,
        saves=row.saves or 0,
        minutes_played=row.minutes_played or 0,
    )


def _agg_columns():
    return (
        func.count(GamePlayerStat.id).label("games"),
        func.coalesce(func.sum(GamePlayerStat.goals), 0).label("goals"),
        func.coalesce(func.sum(GamePlayerStat.assists), 0).label("assists"),
        func.coalesce(func.sum(GamePlayerStat.penalties), 0).label("penalties"),
        func.coalesce(func.sum(GamePlayerStat.goals_against), 0).label("goals_against"),
        func.coalesce(func.sum(GamePlayerStat.saves), 0).label("saves"),
        func.coalesce(func.sum(GamePlayerStat.minutes_played), 0).label("minutes_played"),
    )


async def player_breakdown(
    db: AsyncSession,
    player_id: int,
    *,
    competition_id: int | None = None,
    team_id: int | None = None,
) -> PlayerStatsBreakdown:
    base = (
        select(*_agg_columns())
        .select_from(GamePlayerStat)
        .join(Game, Game.id == GamePlayerStat.game_id)
        .where(GamePlayerStat.player_id == player_id)
    )
    if competition_id is not None:
        base = base.where(Game.competition_id == competition_id)
    if team_id is not None:
        base = base.where(GamePlayerStat.team_id == team_id)

    career_row = (await db.execute(base)).one()
    career = _totals_from_row(career_row)

    # По соревнованиям
    by_comp_res = await db.execute(
        select(Competition.id, Competition.name, *_agg_columns())
        .select_from(GamePlayerStat)
        .join(Game, Game.id == GamePlayerStat.game_id)
        .join(Competition, Competition.id == Game.competition_id)
        .where(GamePlayerStat.player_id == player_id)
        .group_by(Competition.id, Competition.name)
        .order_by(Competition.id)
    )
    by_competition = [
        PlayerCompetitionStat(
            competition_id=r.id, competition_name=r.name, totals=_totals_from_row(r)
        )
        for r in by_comp_res.all()
    ]

    # По командам
    by_team_res = await db.execute(
        select(Team.id, Team.name, *_agg_columns())
        .select_from(GamePlayerStat)
        .join(Team, Team.id == GamePlayerStat.team_id)
        .where(GamePlayerStat.player_id == player_id)
        .group_by(Team.id, Team.name)
        .order_by(Team.name)
    )
    by_team = [
        PlayerTeamStat(team_id=r.id, team_name=r.name, totals=_totals_from_row(r))
        for r in by_team_res.all()
    ]

    return PlayerStatsBreakdown(
        player_id=player_id, career=career, by_competition=by_competition, by_team=by_team
    )


async def competition_players_with_stats(db: AsyncSession, competition_id: int) -> list[dict]:
    """Состав соревнования + агрегированная статистика каждого игрока в нём."""
    from sqlalchemy.orm import selectinload

    from app.models import CompetitionPlayer

    roster_res = await db.execute(
        select(CompetitionPlayer)
        .where(CompetitionPlayer.competition_id == competition_id)
        .options(selectinload(CompetitionPlayer.player))
        .order_by(CompetitionPlayer.team_id, CompetitionPlayer.number)
    )
    roster = roster_res.scalars().all()

    # агрегаты по (player_id, team_id) в рамках соревнования
    agg_res = await db.execute(
        select(
            GamePlayerStat.player_id,
            GamePlayerStat.team_id,
            func.count(GamePlayerStat.id).label("games"),
            func.coalesce(func.sum(GamePlayerStat.goals), 0).label("goals"),
            func.coalesce(func.sum(GamePlayerStat.assists), 0).label("assists"),
            func.coalesce(func.sum(GamePlayerStat.penalties), 0).label("penalties"),
        )
        .select_from(GamePlayerStat)
        .join(Game, Game.id == GamePlayerStat.game_id)
        .where(Game.competition_id == competition_id)
        .group_by(GamePlayerStat.player_id, GamePlayerStat.team_id)
    )
    stats = {(r.player_id, r.team_id): r for r in agg_res.all()}

    out = []
    for cp in roster:
        s = stats.get((cp.player_id, cp.team_id))
        out.append(
            {
                "player": PlayerRead.model_validate(cp.player),
                "team_id": cp.team_id,
                "number": cp.number,
                "contract": cp.contract,
                "goals": s.goals if s else 0,
                "assists": s.assists if s else 0,
                "points": (s.goals + s.assists) if s else 0,
                "penalties": s.penalties if s else 0,
                "games": s.games if s else 0,
            }
        )
    return out


async def best_players(db: AsyncSession, competition_id: int, *, limit: int = 10) -> list[BestPlayer]:
    res = await db.execute(
        select(
            Player,
            func.coalesce(func.sum(GamePlayerStat.goals), 0).label("goals"),
            func.coalesce(func.sum(GamePlayerStat.assists), 0).label("assists"),
            func.coalesce(func.sum(GamePlayerStat.penalties), 0).label("penalties"),
        )
        .select_from(GamePlayerStat)
        .join(Game, Game.id == GamePlayerStat.game_id)
        .join(Player, Player.id == GamePlayerStat.player_id)
        .where(Game.competition_id == competition_id)
        .group_by(Player.id)
        .order_by(
            (func.coalesce(func.sum(GamePlayerStat.goals), 0)
             + func.coalesce(func.sum(GamePlayerStat.assists), 0)).desc()
        )
        .limit(limit)
    )
    out: list[BestPlayer] = []
    for player, goals, assists, penalties in res.all():
        out.append(
            BestPlayer(
                player=PlayerRead.model_validate(player),
                goals=goals,
                assists=assists,
                points=goals + assists,
                penalties=penalties,
            )
        )
    return out
