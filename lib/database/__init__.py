import logging
from typing import Optional, Union

import databases
import pytz
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert, BIGINT

# re-export
DatabaseURL = databases.DatabaseURL

metadata = sa.MetaData()

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


# -----------------------------------------------------------------------------

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
