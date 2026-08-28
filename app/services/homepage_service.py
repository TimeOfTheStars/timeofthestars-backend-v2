from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Competition, HomepageBlock
from app.models.enums import HomepageBlockType
from app.models.homepage import MAX_HOMEPAGE_BLOCKS
from app.schemas.homepage import HomepageBlockIn, HomepageUpdate
from app.services.competition_service import ValidationError


async def get_blocks(db: AsyncSession) -> Sequence[HomepageBlock]:
    res = await db.execute(
        select(HomepageBlock)
        .options(selectinload(HomepageBlock.competition))
        .order_by(HomepageBlock.position, HomepageBlock.id)
    )
    return res.scalars().all()


def _legacy_to_blocks(data: HomepageUpdate) -> list[HomepageBlockIn]:
    """Старый вид настроек (два флага и два соревнования) — в список блоков.

    Порядок прежней главной: сначала таблица, потом сетка. Флаг без выбранного
    соревнования блока не даёт: показывать было бы нечего.
    """
    blocks: list[HomepageBlockIn] = []
    if data.show_standings and data.standings_competition_id:
        blocks.append(
            HomepageBlockIn(
                type=HomepageBlockType.standings, competition_id=data.standings_competition_id
            )
        )
    if data.show_bracket and data.bracket_competition_id:
        blocks.append(
            HomepageBlockIn(
                type=HomepageBlockType.bracket, competition_id=data.bracket_competition_id
            )
        )
    return blocks


async def replace_blocks(
    db: AsyncSession, blocks: Sequence[HomepageBlockIn]
) -> Sequence[HomepageBlock]:
    """Полностью заменяет набор блоков. Порядок — из порядка списка."""
    if len(blocks) > MAX_HOMEPAGE_BLOCKS:
        raise ValidationError(f"На главной помещается не больше {MAX_HOMEPAGE_BLOCKS} блоков")

    for block in blocks:
        comp = await db.get(Competition, block.competition_id)
        if comp is None:
            raise ValidationError(f"Соревнование {block.competition_id} не найдено")

    for row in (await db.execute(select(HomepageBlock))).scalars().all():
        await db.delete(row)
    await db.flush()

    for position, block in enumerate(blocks, start=1):
        title = (block.title or "").strip() or None
        db.add(
            HomepageBlock(
                position=position,
                type=block.type,
                competition_id=block.competition_id,
                title=title,
            )
        )
    await db.flush()
    return await get_blocks(db)


async def update_settings(db: AsyncSession, data: HomepageUpdate) -> Sequence[HomepageBlock]:
    """blocks=None и без старых полей — ничего не меняем и просто отдаём текущее."""
    if data.blocks is not None:
        return await replace_blocks(db, data.blocks)

    legacy_sent = any(
        getattr(data, field) is not None
        for field in (
            "show_standings",
            "standings_competition_id",
            "show_bracket",
            "bracket_competition_id",
        )
    )
    if legacy_sent:
        return await replace_blocks(db, _legacy_to_blocks(data))
    return await get_blocks(db)


def legacy_view(blocks: Sequence[HomepageBlock]) -> dict:
    """Прежние четыре поля, выведенные из блоков — для уже написанного фронта.

    Берётся первый блок каждого типа: старая главная больше одного и не умела.
    """
    first: dict[HomepageBlockType, HomepageBlock] = {}
    for block in blocks:
        first.setdefault(block.type, block)

    standings = first.get(HomepageBlockType.standings)
    bracket = first.get(HomepageBlockType.bracket)
    return {
        "show_standings": standings is not None,
        "standings_competition_id": standings.competition_id if standings else None,
        "show_bracket": bracket is not None,
        "bracket_competition_id": bracket.competition_id if bracket else None,
    }
