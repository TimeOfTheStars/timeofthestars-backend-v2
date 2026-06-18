from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Competition, CompetitionPlayer, CompetitionTeam
from app.models.enums import CompetitionType
from app.schemas.competition import CompetitionCreate, CompetitionUpdate


class ValidationError(Exception):
    """Доменная ошибка валидации (маппится в 400/409 на уровне API)."""


async def list_competitions(
    db: AsyncSession, *, type_: CompetitionType | None = None, page: int = 1, size: int = 50
) -> tuple[Sequence[Competition], int]:
    q = select(Competition)
    if type_ is not None:
        q = q.where(Competition.type == type_)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    q = q.order_by(Competition.start_date.desc(), Competition.id.desc())
    q = q.offset((page - 1) * size).limit(size)
    items = (await db.execute(q)).scalars().all()
    return items, total


async def get(db: AsyncSession, competition_id: int) -> Competition | None:
    return await db.get(Competition, competition_id)


async def _team_ids(db: AsyncSession, competition_id: int) -> set[int]:
    res = await db.execute(
        select(CompetitionTeam.team_id).where(CompetitionTeam.competition_id == competition_id)
    )
    return set(res.scalars().all())


async def _validate_winner(db: AsyncSession, competition_id: int, winner_team_id: int | None) -> None:
    if winner_team_id is None:
        return
    if winner_team_id not in await _team_ids(db, competition_id):
        raise ValidationError("Победителем может быть только команда-участница соревнования")


async def create(db: AsyncSession, data: CompetitionCreate) -> Competition:
    comp = Competition(**data.model_dump())
    db.add(comp)
    await db.flush()
    return comp


async def update(db: AsyncSession, comp: Competition, data: CompetitionUpdate) -> Competition:
    payload = data.model_dump(exclude_unset=True)
    if "winner_team_id" in payload:
        await _validate_winner(db, comp.id, payload["winner_team_id"])
    for key, value in payload.items():
        setattr(comp, key, value)
    await db.flush()
    return comp


async def delete(db: AsyncSession, comp: Competition) -> None:
    await db.delete(comp)
    await db.flush()


# --- Состав ---
async def add_team(db: AsyncSession, competition_id: int, team_id: int) -> None:
    exists = await db.execute(
        select(CompetitionTeam.id).where(
            CompetitionTeam.competition_id == competition_id,
            CompetitionTeam.team_id == team_id,
        )
    )
    if exists.first() is None:
        db.add(CompetitionTeam(competition_id=competition_id, team_id=team_id))
        await db.flush()


async def remove_team(db: AsyncSession, competition_id: int, team_id: int) -> bool:
    obj = await db.execute(
        select(CompetitionTeam).where(
            CompetitionTeam.competition_id == competition_id,
            CompetitionTeam.team_id == team_id,
        )
    )
    ct = obj.scalar_one_or_none()
    if ct is None:
        return False
    await db.delete(ct)
    await db.flush()
    return True


async def add_player(
    db: AsyncSession,
    competition_id: int,
    team_id: int,
    player_id: int,
    number: int | None,
    contract: bool,
) -> None:
    # команда должна быть в соревновании
    if team_id not in await _team_ids(db, competition_id):
        await add_team(db, competition_id, team_id)
    exists = await db.execute(
        select(CompetitionPlayer.id).where(
            CompetitionPlayer.competition_id == competition_id,
            CompetitionPlayer.team_id == team_id,
            CompetitionPlayer.player_id == player_id,
        )
    )
    if exists.first() is None:
        db.add(
            CompetitionPlayer(
                competition_id=competition_id,
                team_id=team_id,
                player_id=player_id,
                number=number,
                contract=contract,
            )
        )
        await db.flush()


async def remove_player(db: AsyncSession, competition_id: int, team_id: int, player_id: int) -> bool:
    obj = await db.execute(
        select(CompetitionPlayer).where(
            CompetitionPlayer.competition_id == competition_id,
            CompetitionPlayer.team_id == team_id,
            CompetitionPlayer.player_id == player_id,
        )
    )
    cp = obj.scalar_one_or_none()
    if cp is None:
        return False
    await db.delete(cp)
    await db.flush()
    return True


async def _get_roster_player(
    db: AsyncSession, competition_id: int, team_id: int, player_id: int
) -> CompetitionPlayer | None:
    res = await db.execute(
        select(CompetitionPlayer).where(
            CompetitionPlayer.competition_id == competition_id,
            CompetitionPlayer.team_id == team_id,
            CompetitionPlayer.player_id == player_id,
        )
    )
    return res.scalar_one_or_none()


async def set_player_contract(
    db: AsyncSession, competition_id: int, team_id: int, player_id: int, contract: bool
) -> bool:
    cp = await _get_roster_player(db, competition_id, team_id, player_id)
    if cp is None:
        return False
    cp.contract = contract
    await db.flush()
    return True


async def update_roster_player(
    db: AsyncSession,
    competition_id: int,
    team_id: int,
    player_id: int,
    *,
    number: int | None = None,
    contract: bool | None = None,
    set_number: bool = False,
) -> bool:
    """Обновляет данные заявки игрока. `set_number=True` позволяет выставить
    номер в т.ч. в None (снять номер)."""
    cp = await _get_roster_player(db, competition_id, team_id, player_id)
    if cp is None:
        return False
    if set_number:
        cp.number = number
    if contract is not None:
        cp.contract = contract
    await db.flush()
    return True


async def get_roster(db: AsyncSession, competition_id: int) -> Sequence[CompetitionTeam]:
    """Команды соревнования с подгруженными командами (для составов)."""
    res = await db.execute(
        select(CompetitionTeam)
        .where(CompetitionTeam.competition_id == competition_id)
        .options(selectinload(CompetitionTeam.team))
    )
    return res.scalars().all()


async def get_players(db: AsyncSession, competition_id: int) -> Sequence[CompetitionPlayer]:
    res = await db.execute(
        select(CompetitionPlayer)
        .where(CompetitionPlayer.competition_id == competition_id)
        .options(selectinload(CompetitionPlayer.player), selectinload(CompetitionPlayer.team))
        .order_by(CompetitionPlayer.team_id, CompetitionPlayer.number)
    )
    return res.scalars().all()
