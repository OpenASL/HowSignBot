"""add include_clthat and name

Revision ID: b1014cab80a9
Revises: f9c59562a31a
Create Date: 2020-11-20 19:19:45.578853

"""
from alembic import op
import sqlalchemy as sa
from bot import database


# revision identifiers, used by Alembic.
revision = "b1014cab80a9"
down_revision = "f9c59562a31a"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "guild_settings",
        sa.Column(
            "include_clthat",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column("guild_settings", sa.Column("name", sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("guild_settings", "name")
    op.drop_column("guild_settings", "include_clthat")
    # ### end Alembic commands ###
