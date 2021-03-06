"""add participant created_at

Revision ID: 5802c6bd278a
Revises: 052cd0f20b47
Create Date: 2021-02-21 13:19:52.409718

"""
from alembic import op
import sqlalchemy as sa
from bot import database


# revision identifiers, used by Alembic.
revision = "5802c6bd278a"
down_revision = "052cd0f20b47"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "zoom_participants",
        sa.Column("created_at", database.TIMESTAMP(timezone=True), nullable=True),
    )
    op.execute("UPDATE zoom_participants SET created_at = 'epoch'")
    op.alter_column("zoom_participants", "created_at", nullable=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("zoom_participants", "created_at")
    # ### end Alembic commands ###
