"""add topics

Revision ID: 816ea3631582
Revises: 37a124b0099b
Create Date: 2021-03-13 14:20:10.044131

"""
from alembic import op
import sqlalchemy as sa
import bot


# revision identifiers, used by Alembic.
revision = "816ea3631582"
down_revision = "37a124b0099b"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "topics",
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("last_synced_at", bot.database.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("content"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("topics")
    # ### end Alembic commands ###
