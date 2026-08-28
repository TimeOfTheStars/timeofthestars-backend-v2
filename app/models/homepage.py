from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import HomepageBlockType

# Сколько блоков помещается на главной. Ограничение продуктовое, а не техническое:
# проверяется в homepage_service, в схеме БД его нет.
MAX_HOMEPAGE_BLOCKS = 3


class HomepageBlock(Base, TimestampMixin):
    """Блок главного экрана: таблица или сетка конкретного соревнования.

    Порядок задаётся полем position (1, 2, 3 …) — его проставляет сервер по
    порядку присланного списка, клиент им не управляет.
    """

    __tablename__ = "homepage_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[HomepageBlockType] = mapped_column(
        Enum(HomepageBlockType, native_enum=False, length=20), nullable=False
    )
    # Блок без соревнования бессмыслен, поэтому CASCADE: удалили соревнование —
    # блок уходит вместе с ним, а не превращается в пустой заголовок.
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Пусто — фронт показывает название соревнования
    title: Mapped[str | None] = mapped_column(String, nullable=True)

    competition = relationship("Competition")
