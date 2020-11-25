"""add guild settings

Revision ID: f9c59562a31a
Revises: 90f23f127d05
Create Date: 2020-11-19 00:12:17.159256

"""
import json
from base64 import b64decode

from alembic import op
import sqlalchemy as sa
from environs import Env


# revision identifiers, used by Alembic.
revision = "f9c59562a31a"
down_revision = "90f23f127d05"
branch_labels = None
depends_on = None

env = Env()
env.read_env()


def decode_settings(encoded):
    return json.loads(b64decode(encoded))


GUILD_SETTINGS = env.str("GUILD_SETTINGS", None)


def load_table(connection, table):
    return sa.Table(table, sa.MetaData(), autoload_with=connection)


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "guild_settings",
        sa.Column("guild_id", sa.BIGINT(), nullable=False),
        sa.Column("schedule_sheet_key", sa.Text(), nullable=True),
        sa.Column("daily_message_channel_id", sa.BIGINT(), nullable=True),
        sa.Column(
            "include_handshape_of_the_day",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "include_topics_of_the_day",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("guild_id"),
    )
    # ### end Alembic commands ###
    if GUILD_SETTINGS:
        values = decode_settings(GUILD_SETTINGS)
        connection = op.get_bind()
        guild_settings = load_table(connection, "guild_settings")
        connection.execute(guild_settings.insert().values(values))


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("guild_settings")
    # ### end Alembic commands ###