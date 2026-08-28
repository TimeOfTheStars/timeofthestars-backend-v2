"""homepage blocks and game team stats

Главная перестаёт быть синглтоном с двумя переключателями: вместо
homepage_settings появляется список блоков (до трёх, порядок задаёт админ).
Прежняя настройка переносится в блоки, поэтому главная после миграции
выглядит так же, как до неё.

Плюс game_team_stats — командные итоги матча (броски, броски в створ,
вбрасывания, реализация). Штрафные минуты сюда не попадают: они и дальше
выводятся из событий.

Revision ID: b47c9e0d21fa
Revises: 8f3a1c7d5b2e
Create Date: 2026-08-29 01:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b47c9e0d21fa"
down_revision: str | None = "8f3a1c7d5b2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP_DEFAULT = sa.text("(CURRENT_TIMESTAMP)")


def upgrade() -> None:
    op.create_table(
        "homepage_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "standings",
                "bracket",
                name="homepageblocktype",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("competition_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=TIMESTAMP_DEFAULT, nullable=False),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_homepage_blocks_competition_id"),
        "homepage_blocks",
        ["competition_id"],
        unique=False,
    )

    # Переносим прежнюю настройку: сначала таблица, потом сетка — в том порядке,
    # в каком старая главная их и показывала. Флаг без соревнования блока не даёт.
    op.execute(
        """
        INSERT INTO homepage_blocks (position, type, competition_id)
        SELECT 1, 'standings', standings_competition_id
        FROM homepage_settings
        WHERE show_standings AND standings_competition_id IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO homepage_blocks (position, type, competition_id)
        SELECT
            (SELECT COUNT(*) FROM homepage_blocks) + 1, 'bracket', bracket_competition_id
        FROM homepage_settings
        WHERE show_bracket AND bracket_competition_id IS NOT NULL
        """
    )
    op.drop_table("homepage_settings")

    op.create_table(
        "game_team_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("shots", sa.Integer(), nullable=True),
        sa.Column("shots_on_goal", sa.Integer(), nullable=True),
        sa.Column("faceoffs_won", sa.Integer(), nullable=True),
        sa.Column("conversion_percent", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=TIMESTAMP_DEFAULT, nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "team_id", name="uq_game_team"),
    )
    op.create_index(
        op.f("ix_game_team_stats_game_id"), "game_team_stats", ["game_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_game_team_stats_game_id"), table_name="game_team_stats")
    op.drop_table("game_team_stats")

    op.create_table(
        "homepage_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("show_bracket", sa.Boolean(), nullable=False),
        sa.Column("bracket_competition_id", sa.Integer(), nullable=True),
        sa.Column("show_standings", sa.Boolean(), nullable=False),
        sa.Column("standings_competition_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=TIMESTAMP_DEFAULT, nullable=False),
        sa.ForeignKeyConstraint(
            ["bracket_competition_id"], ["competitions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["standings_competition_id"], ["competitions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Возвращаем синглтон: берём первый блок каждого типа, остальные теряются —
    # старая схема больше одного и не умела.
    op.execute(
        """
        INSERT INTO homepage_settings (
            id, show_bracket, bracket_competition_id, show_standings, standings_competition_id
        )
        VALUES (
            1,
            EXISTS (SELECT 1 FROM homepage_blocks WHERE type = 'bracket'),
            (SELECT competition_id FROM homepage_blocks WHERE type = 'bracket'
             ORDER BY position, id LIMIT 1),
            EXISTS (SELECT 1 FROM homepage_blocks WHERE type = 'standings'),
            (SELECT competition_id FROM homepage_blocks WHERE type = 'standings'
             ORDER BY position, id LIMIT 1)
        )
        """
    )

    op.drop_index(op.f("ix_homepage_blocks_competition_id"), table_name="homepage_blocks")
    op.drop_table("homepage_blocks")
