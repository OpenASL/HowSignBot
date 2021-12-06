"""add include_practice_schedule

Revision ID: ad375ea654d5
Revises: 60ad67ade014
Create Date: 2021-11-20 12:23:52.856895

"""
from alembic import op
import sqlalchemy as sa
import bot


# revision identifiers, used by Alembic.
revision = "ad375ea654d5"
down_revision = "60ad67ade014"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "guild_settings",
        sa.Column(
            "include_practice_schedule",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("guild_settings", "include_practice_schedule")
    # ### end Alembic commands ###