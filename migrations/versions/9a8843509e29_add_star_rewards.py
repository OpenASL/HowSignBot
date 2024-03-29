"""add star_rewards

Revision ID: 9a8843509e29
Revises: 5d3fdf926fe6
Create Date: 2022-02-23 20:03:26.791586

"""
from alembic import op
import sqlalchemy as sa
import bot
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "9a8843509e29"
down_revision = "5d3fdf926fe6"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "star_rewards",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BIGINT(), nullable=False),
        sa.Column("star_count", sa.Integer(), nullable=False),
        sa.Column("created_at", bot.database.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "guild_settings",
        sa.Column(
            "reward_milestones",
            postgresql.ARRAY(sa.Integer()),
            server_default="{}",
            nullable=False,
        ),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("guild_settings", "reward_milestones")
    op.drop_table("star_rewards")
    # ### end Alembic commands ###
