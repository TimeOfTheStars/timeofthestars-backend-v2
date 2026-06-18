from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HomepageSettings
from app.schemas.homepage import HomepageUpdate

SINGLETON_ID = 1


async def get_settings(db: AsyncSession) -> HomepageSettings:
    res = await db.execute(select(HomepageSettings).where(HomepageSettings.id == SINGLETON_ID))
    settings_row = res.scalar_one_or_none()
    if settings_row is None:
        settings_row = HomepageSettings(id=SINGLETON_ID)
        db.add(settings_row)
        await db.flush()
    return settings_row


async def update_settings(db: AsyncSession, data: HomepageUpdate) -> HomepageSettings:
    row = await get_settings(db)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.flush()
    return row
