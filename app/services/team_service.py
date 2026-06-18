from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Team
from app.schemas.team import TeamCreate, TeamUpdate
from app.services.utils import slugify


async def _unique_slug(db: AsyncSession, base: str, exclude_id: int | None = None) -> str:
    slug = slugify(base)
    candidate = slug
    i = 2
    while True:
        q = select(Team.id).where(Team.slug == candidate)
        if exclude_id is not None:
            q = q.where(Team.id != exclude_id)
        if (await db.execute(q)).first() is None:
            return candidate
        candidate = f"{slug}-{i}"
        i += 1


async def list_teams(
    db: AsyncSession, *, page: int = 1, size: int = 50, search: str | None = None
) -> tuple[Sequence[Team], int]:
    q = select(Team)
    if search:
        like = f"%{search}%"
        q = q.where(or_(Team.name.ilike(like), Team.city.ilike(like)))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    q = q.order_by(Team.name).offset((page - 1) * size).limit(size)
    items = (await db.execute(q)).scalars().all()
    return items, total


async def get(db: AsyncSession, team_id: int) -> Team | None:
    return await db.get(Team, team_id)


async def create(db: AsyncSession, data: TeamCreate) -> Team:
    slug = await _unique_slug(db, data.slug or data.name)
    team = Team(name=data.name, slug=slug, city=data.city, logo_url=data.logo_url)
    db.add(team)
    await db.flush()
    return team


async def update(db: AsyncSession, team: Team, data: TeamUpdate) -> Team:
    payload = data.model_dump(exclude_unset=True)
    if "slug" in payload and payload["slug"]:
        payload["slug"] = await _unique_slug(db, payload["slug"], exclude_id=team.id)
    for key, value in payload.items():
        setattr(team, key, value)
    await db.flush()
    return team


async def delete(db: AsyncSession, team: Team) -> None:
    await db.delete(team)
    await db.flush()
