import logging
from typing import Optional, Union, Iterator

import databases
import pytz
from databases.backends.postgres import Record
import sqlalchemy as sa
from sqlalchemy import sql
from sqlalchemy.dialects.postgresql import insert, BIGINT, TIMESTAMP as _TIMESTAMP

# re-export
DatabaseURL = databases.DatabaseURL

metadata = sa.MetaData()
NULL = sql.null()

logger = logging.getLogger(__name__)


class TimeZone(sa.TypeDecorator):
    impl = sa.Text

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return pytz.timezone(value)


class TIMESTAMP(sa.TypeDecorator):
    impl = _TIMESTAMP(timezone=True)


# -----------------------------------------------------------------------------

guild_settings = sa.Table(
    "guild_settings",
    metadata,
    sa.Column("guild_id", BIGINT, primary_key=True),
    sa.Column("name", sa.Text),  # Not used, just for ease of use
    sa.Column("schedule_sheet_key", sa.Text),
    sa.Column("daily_message_channel_id", BIGINT),
    sa.Column(
        "include_handshape_of_the_day",
        sa.Boolean,
        server_default=sql.false(),
        nullable=False,
    ),
    sa.Column(
        "include_topics_of_the_day",
        sa.Boolean,
        server_default=sql.false(),
        nullable=False,
    ),
    sa.Column(
        "include_clthat",
        sa.Boolean,
        server_default=sql.false(),
        nullable=False,
    ),
)

user_settings = sa.Table(
    "user_settings",
    metadata,
    sa.Column("user_id", BIGINT, primary_key=True),
    sa.Column("timezone", TimeZone),
)

# -----------------------------------------------------------------------------


class Store:
    metadata = metadata

    def __init__(
        self,
        database_url: Union[str, databases.DatabaseURL],
        *,
        force_rollback: bool = False,
    ):
        self.db = databases.Database(database_url, force_rollback=force_rollback)

    def connect(self):
        return self.db.connect()

    def disconnect(self):
        return self.db.disconnect()

    async def set_user_timezone(self, user_id: int, timezone: Optional[pytz.BaseTzInfo]):
        logger.info(f"setting timezone for user_id {user_id}")
        stmt = insert(user_settings).values(user_id=user_id, timezone=timezone)
        stmt = stmt.on_conflict_do_update(
            index_elements=(user_settings.c.user_id,),
            set_=dict(timezone=stmt.excluded.timezone),
        )
        await self.db.execute(stmt)

    async def get_user_timezone(self, user_id: int) -> Optional[pytz.BaseTzInfo]:
        logger.info(f"retrieving timezone for user_id {user_id}")
        query = user_settings.select().where(user_settings.c.user_id == user_id)
        return await self.db.fetch_val(query=query, column=user_settings.c.timezone)

    async def get_guild_settings(self, guild_id: int) -> Record:
        logger.info(f"retrieving guild settings sheet key for guild_id {guild_id}")
        query = guild_settings.select().where(guild_settings.c.guild_id == guild_id)
        return await self.db.fetch_one(query=query)

    async def get_guild_schedule_sheet_key(self, guild_id: int) -> Optional[str]:
        query = guild_settings.select().where(guild_settings.c.guild_id == guild_id)
        return await self.db.fetch_val(
            query=query, column=guild_settings.c.schedule_sheet_key
        )

    async def guild_has_practice_schedule(self, guild_id: int) -> bool:
        select = sa.select(
            (
                sa.exists()
                .where(
                    (guild_settings.c.guild_id == guild_id)
                    & (guild_settings.c.schedule_sheet_key != NULL)
                )
                .label("result"),
            )
        )
        record = await self.db.fetch_one(select)
        return record.get("result")

    async def get_daily_message_channel_ids(self) -> Iterator[int]:
        all_settings = await self.db.fetch_all(
            guild_settings.select().where(
                guild_settings.c.daily_message_channel_id != NULL
            )
        )
        return (record.get("daily_message_channel_id") for record in all_settings)
