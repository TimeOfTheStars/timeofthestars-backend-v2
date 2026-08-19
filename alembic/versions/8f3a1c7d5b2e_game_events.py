"""game events timeline

Revision ID: 8f3a1c7d5b2e
Revises: e221e1568692
Create Date: 2026-08-19 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f3a1c7d5b2e"
down_revision: str | None = "e221e1568692"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "goal",
                "shootout_goal",
                "penalty",
                "goalie_change",
                name="gameeventtype",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("time_seconds", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("assist1_player_id", sa.Integer(), nullable=True),
        sa.Column("assist2_player_id", sa.Integer(), nullable=True),
        sa.Column("video_seconds", sa.Integer(), nullable=True),
        sa.Column("penalty_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["assist1_player_id"], ["players.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assist2_player_id"], ["players.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_game_events_game_id"), "game_events", ["game_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_game_events_game_id"), table_name="game_events")
    op.drop_table("game_events")
