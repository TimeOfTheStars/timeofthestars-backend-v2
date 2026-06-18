from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Game, GamePlayerStat
from app.models.enums import GameStatus
from app.schemas.game import GameCreate, GameUpdate, ProtocolRequest
from app.services.competition_service import ValidationError


def _maybe_finish(game: Game) -> None:
    """Игра считается сыгранной, как только проставлен счёт обеих команд."""
    if game.score_team_a is not None and game.score_team_b is not None:
        game.status = GameStatus.finished


async def list_games(
    db: AsyncSession, *, competition_id: int | None = None, team_id: int | None = None
) -> Sequence[Game]:
    q = select(Game)
    if competition_id is not None:
        q = q.where(Game.competition_id == competition_id)
    if team_id is not None:
        q = q.where((Game.team_a_id == team_id) | (Game.team_b_id == team_id))
    q = q.order_by(Game.date, Game.time, Game.id)
    return (await db.execute(q)).scalars().all()


async def get(db: AsyncSession, game_id: int) -> Game | None:
    return await db.get(Game, game_id)


async def games_for_player(db: AsyncSession, player_id: int) -> Sequence[Game]:
    res = await db.execute(
        select(Game)
        .join(GamePlayerStat, GamePlayerStat.game_id == Game.id)
        .where(GamePlayerStat.player_id == player_id)
        .order_by(Game.date, Game.time)
    )
    return res.scalars().unique().all()


async def get_with_protocol(db: AsyncSession, game_id: int) -> Game | None:
    res = await db.execute(
        select(Game)
        .where(Game.id == game_id)
        .options(selectinload(Game.player_stats).selectinload(GamePlayerStat.player))
    )
    return res.scalar_one_or_none()


async def create(db: AsyncSession, data: GameCreate) -> Game:
    game = Game(**data.model_dump())
    _maybe_finish(game)
    db.add(game)
    await db.flush()
    return game


async def update(db: AsyncSession, game: Game, data: GameUpdate) -> Game:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(game, key, value)
    _maybe_finish(game)
    await db.flush()
    return game


async def delete(db: AsyncSession, game: Game) -> None:
    await db.delete(game)
    await db.flush()


async def save_protocol(db: AsyncSession, game: Game, data: ProtocolRequest) -> Game:
    """Полностью заменяет протокол матча (счёт + строки по игрокам)."""
    valid_teams = {game.team_a_id, game.team_b_id}
    for line in data.stat_lines:
        if line.team_id not in valid_teams:
            raise ValidationError(
                f"Игрок {line.player_id}: команда {line.team_id} не участвует в этом матче"
            )

    if data.score_team_a is not None:
        game.score_team_a = data.score_team_a
    if data.score_team_b is not None:
        game.score_team_b = data.score_team_b
    if data.bullet_win_team_id is not None:
        game.bullet_win_team_id = data.bullet_win_team_id
    _maybe_finish(game)

    # удаляем старые строки протокола
    existing = (
        await db.execute(select(GamePlayerStat).where(GamePlayerStat.game_id == game.id))
    ).scalars().all()
    for row in existing:
        await db.delete(row)
    await db.flush()

    for line in data.stat_lines:
        db.add(GamePlayerStat(game_id=game.id, **line.model_dump()))
    await db.flush()
    return game
