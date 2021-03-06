"""add topics

Revision ID: 90f23f127d05
Revises: a429443e6c16
Create Date: 2020-11-17 23:49:07.131973

"""
from alembic import op
import sqlalchemy as sa
from bot import database


# revision identifiers, used by Alembic.
revision = "90f23f127d05"
down_revision = "a429443e6c16"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content"),
    )
    op.create_table(
        "topic_usages",
        sa.Column("guild_id", sa.BIGINT(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("last_used_at", database.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("guild_id", "topic_id"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("topic_usages")
    op.drop_table("topics")
    # ### end Alembic commands ###
