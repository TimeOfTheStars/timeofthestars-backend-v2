from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import HomepageBlockType
from app.models.homepage import MAX_HOMEPAGE_BLOCKS
from app.schemas.competition import CompetitionBrief


class HomepageBlockIn(BaseModel):
    """Блок главной на вход. position не передаётся: порядок берётся из массива."""

    model_config = ConfigDict(extra="forbid")

    type: HomepageBlockType
    competition_id: int
    title: str | None = None


class HomepageBlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    type: HomepageBlockType
    competition_id: int
    title: str | None = None
    competition: CompetitionBrief | None = None


class HomepageUpdate(BaseModel):
    """blocks=None — блоки не трогаем, [] — очищаем главную.

    Четыре поля ниже — прежний вид настроек. Они по-прежнему принимаются, чтобы
    не ломать уже написанный фронт, и переводятся в блоки: сначала таблица,
    потом сетка. Если передан blocks, старые поля игнорируются.
    """

    blocks: list[HomepageBlockIn] | None = Field(default=None, max_length=MAX_HOMEPAGE_BLOCKS)

    show_standings: bool | None = None
    standings_competition_id: int | None = None
    show_bracket: bool | None = None
    bracket_competition_id: int | None = None


class HomepageRead(BaseModel):
    """Блоки — источник истины, четыре поля ниже выводятся из них для старого фронта."""

    blocks: list[HomepageBlockRead] = []

    show_standings: bool = False
    standings_competition_id: int | None = None
    show_bracket: bool = False
    bracket_competition_id: int | None = None
