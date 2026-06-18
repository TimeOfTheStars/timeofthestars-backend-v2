from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Player
from app.schemas.player import PlayerCreate, PlayerUpdate


async def list_players(
    db: AsyncSession, *, page: int = 1, size: int = 50, search: str | None = None
) -> tuple[Sequence[Player], int]:
    q = select(Player)
    if search:
        q = q.where(Player.full_name.ilike(f"%{search}%"))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    q = q.order_by(Player.full_name).offset((page - 1) * size).limit(size)
    items = (await db.execute(q)).scalars().all()
    return items, total


async def get(db: AsyncSession, player_id: int) -> Player | None:
    return await db.get(Player, player_id)


async def create(db: AsyncSession, data: PlayerCreate) -> Player:
    player = Player(**data.model_dump())
    db.add(player)
    await db.flush()
    return player


async def update(db: AsyncSession, player: Player, data: PlayerUpdate) -> Player:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(player, key, value)
    await db.flush()
    return player


async def delete(db: AsyncSession, player: Player) -> None:
    await db.delete(player)
    await db.flush()
