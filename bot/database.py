import datetime as dt
import logging
from typing import Iterator
from typing import List
from typing import Mapping
from typing import Optional
from typing import Sequence
from typing import Union

import databases
import nanoid
import pytz
import sqlalchemy as sa
from sqlalchemy import sql
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.dialects.postgresql import TIMESTAMP as _TIMESTAMP
from sqlalchemy.sql.schema import ForeignKey

from . import settings

metadata = sa.MetaData()
NULL = sql.null()

logger = logging.getLogger(__name__)


def now():
    return dt.datetime.now(dt.timezone.utc)


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


def created_at_column(name="created_at", **kwargs):
    return sa.Column(name, TIMESTAMP, nullable=False, default=now, **kwargs)


NANOID_ALPHABET = "23456789abcdefghijkmnopqrstuvwxyz"
NANOID_SIZE = 5


def generate_nanoid() -> str:
    return nanoid.generate(alphabet=NANOID_ALPHABET, size=NANOID_SIZE)


# -----------------------------------------------------------------------------

guild_settings = sa.Table(
    "guild_settings",
    metadata,
    sa.Column("guild_id", BIGINT, primary_key=True, doc="Discord guild ID"),
    sa.Column("name", sa.Text, doc="Name of the guild, for readability in clients"),
    sa.Column(
        "schedule_sheet_key",
        sa.Text,
        doc="Google sheet key for the guild's practice schedule",
    ),
    sa.Column(
        "daily_message_channel_id",
        BIGINT,
        doc="Discord channel ID where to post daily schedule message.",
    ),
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
    sa.Column("user_id", BIGINT, primary_key=True, doc="Discord user ID"),
    sa.Column("timezone", TimeZone),
)

aslpp_intros = sa.Table(
    "aslpp_intros",
    metadata,
    sa.Column("message_id", BIGINT, primary_key=True, doc="Discord message ID"),
    sa.Column("user_id", BIGINT, index=True, nullable=False, doc="Discord user ID"),
    sa.Column("posted_at", TIMESTAMP, nullable=False),
    created_at_column(),
)

aslpp_members = sa.Table(
    "aslpp_members",
    metadata,
    sa.Column("user_id", BIGINT, primary_key=True, doc="Discord user ID"),
    sa.Column("joined_at", TIMESTAMP, nullable=False),
    sa.Column("last_message_at", TIMESTAMP, nullable=True),
    sa.Column("is_active", sa.Boolean, nullable=False, server_default=sql.false()),
    created_at_column(),
)

zoom_meetings = sa.Table(
    "zoom_meetings",
    metadata,
    sa.Column("meeting_id", BIGINT, primary_key=True, doc="Meeting ID issued by Zoom"),
    sa.Column("zoom_user", sa.Text, nullable=False),
    sa.Column("join_url", sa.Text, nullable=False),
    sa.Column("passcode", sa.Text, nullable=False),
    sa.Column("topic", sa.Text, nullable=False),
    sa.Column("host_id", sa.Text, doc="Last cached zoom ID of the host"),
    sa.Column("setup_at", TIMESTAMP),
    created_at_column(),
)

zzzzoom_meetings = sa.Table(
    "zzzzoom_meetings",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column(
        "meeting_id",
        ForeignKey(zoom_meetings.c.meeting_id, ondelete="CASCADE"),
        index=True,
    ),
    created_at_column(),
)

zoom_messages = sa.Table(
    "zoom_messages",
    metadata,
    sa.Column("message_id", BIGINT, primary_key=True, doc="Discord message ID"),
    sa.Column("channel_id", BIGINT, nullable=False, doc="Discord channel ID"),
    sa.Column("meeting_id", ForeignKey(zoom_meetings.c.meeting_id, ondelete="CASCADE")),
    created_at_column(),
)

zoom_participants = sa.Table(
    "zoom_participants",
    metadata,
    sa.Column(
        "meeting_id",
        ForeignKey(zoom_meetings.c.meeting_id, ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("name", sa.Text, primary_key=True),
    sa.Column("zoom_id", sa.Text, doc="Zoom user ID (null for non-registered users)"),
    sa.Column("email", sa.Text, doc="Zoom email (null for non-registered users)"),
    sa.Column(
        "joined_at",
        TIMESTAMP,
        doc="Join time from webhook payload. Unlike created_at, this will be updated when a participant is moved to and from a breakout room.",
    ),
    created_at_column(),
)

topics = sa.Table(
    "topics",
    metadata,
    sa.Column("content", sa.Text, primary_key=True),
    sa.Column("last_synced_at", TIMESTAMP),
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

    def transaction(self):
        return self.db.transaction()

    async def set_user_timezone(self, user_id: int, timezone: Optional[dt.tzinfo]):
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

    async def get_guild_settings(self, guild_id: int) -> Optional[Mapping]:
        logger.info(f"retrieving guild settings sheet key for guild_id {guild_id}")
        query = guild_settings.select().where(guild_settings.c.guild_id == guild_id)
        return await self.db.fetch_one(query=query)

    async def get_guild_schedule_sheet_key(self, guild_id: int) -> Optional[str]:
        query = guild_settings.select().where(guild_settings.c.guild_id == guild_id)
        return await self.db.fetch_val(
            query=query, column=guild_settings.c.schedule_sheet_key
        )

    async def get_guild_daily_message_channel_id(self, guild_id: int) -> Optional[int]:
        query = guild_settings.select().where(guild_settings.c.guild_id == guild_id)
        return await self.db.fetch_val(
            query=query, column=guild_settings.c.daily_message_channel_id
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
        if not record:
            return False
        return record["result"]

    async def get_guild_ids_with_practice_schedules(self) -> Iterator[int]:
        all_settings = await self.db.fetch_all(
            guild_settings.select().where(
                guild_settings.c.daily_message_channel_id != NULL
            )
        )
        return (record["guild_id"] for record in all_settings)

    async def get_daily_message_channel_ids(self) -> Iterator[int]:
        all_settings = await self.db.fetch_all(
            guild_settings.select().where(
                guild_settings.c.daily_message_channel_id != NULL
            )
        )
        return (record["daily_message_channel_id"] for record in all_settings)

    # Zoom

    async def create_zoom_meeting(
        self,
        *,
        zoom_user: str,
        meeting_id: int,
        join_url: str,
        passcode: str,
        topic: str,
        set_up: bool,
    ):
        created_at = now()
        stmt = insert(zoom_meetings).values(
            zoom_user=zoom_user,
            meeting_id=meeting_id,
            join_url=join_url,
            passcode=passcode,
            topic=topic,
            # NOTE: need to pass created_at because default=now
            #  doesn't have an effect when using postgresql.insert
            created_at=created_at,
            setup_at=created_at if set_up else None,
        )
        await self.db.execute(stmt)

    async def get_zoom_meeting(self, meeting_id: int) -> Optional[Mapping]:
        query = zoom_meetings.select().where(zoom_meetings.c.meeting_id == meeting_id)
        return await self.db.fetch_one(query=query)

    async def get_latest_pending_zoom_meeting_for_user(
        self, zoom_user: str
    ) -> Optional[Mapping]:
        query = (
            zoom_meetings.select()
            .where(
                (zoom_meetings.c.zoom_user == zoom_user)
                & (zoom_meetings.c.setup_at == NULL)
            )
            .order_by(zoom_meetings.c.created_at.desc())
        )
        return await self.db.fetch_one(query=query)

    async def set_up_zoom_meeting(self, meeting_id: int):
        await self.db.execute(
            zoom_meetings.update()
            .where(zoom_meetings.c.meeting_id == meeting_id)
            .values(setup_at=now())
        )

    async def end_zoom_meeting(self, meeting_id: int):
        await self.db.execute(
            zoom_meetings.delete().where(zoom_meetings.c.meeting_id == meeting_id)
        )
        await self.db.execute(
            zoom_messages.delete().where(zoom_messages.c.meeting_id == meeting_id)
        )
        await self.db.execute(
            zzzzoom_meetings.delete().where(zzzzoom_meetings.c.meeting_id == meeting_id)
        )

    async def set_zoom_meeting_host_id(self, meeting_id: int, *, host_id: str):
        await self.db.execute(
            zoom_meetings.update()
            .where(zoom_meetings.c.meeting_id == meeting_id)
            .values(host_id=host_id)
        )

    async def zoom_meeting_exists(self, meeting_id: int) -> bool:
        select = sa.select(
            (sa.exists().where(zoom_meetings.c.meeting_id == meeting_id).label("result"),)
        )
        record = await self.db.fetch_one(select)
        if not record:
            return False
        return record["result"]

    async def create_zoom_message(
        self, *, meeting_id: int, message_id: int, channel_id: int
    ):
        await self.db.execute(
            insert(zoom_messages).values(
                meeting_id=meeting_id,
                message_id=message_id,
                channel_id=channel_id,
                # NOTE: need to pass created_at because default=now
                #  doesn't have an effect when using postgresql.insert
                created_at=now(),
            )
        )

    async def remove_zoom_message(self, *, message_id: int):
        await self.db.execute(
            zoom_messages.delete().where(zoom_messages.c.message_id == message_id)
        )

    async def get_zoom_message(self, message_id: int) -> Optional[Mapping]:
        return await self.db.fetch_one(
            zoom_messages.select().where(zoom_messages.c.message_id == message_id)
        )

    async def get_zoom_messages(self, meeting_id: int) -> List[Mapping]:
        return await self.db.fetch_all(
            zoom_messages.select().where(zoom_messages.c.meeting_id == meeting_id)
        )

    async def add_zoom_participant(
        self,
        *,
        meeting_id: int,
        name: str,
        zoom_id: Optional[str],
        email: Optional[str],
        joined_at: dt.datetime,
    ):
        stmt = insert(zoom_participants).values(
            meeting_id=meeting_id,
            name=name,
            zoom_id=zoom_id,
            email=email,
            joined_at=joined_at,
            # NOTE: need to pass created_at because `default` doesn't execute
            #  when using postgres's insert
            created_at=now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=(zoom_participants.c.meeting_id, zoom_participants.c.name),
            set_=dict(
                zoom_id=stmt.excluded.zoom_id,
                email=stmt.excluded.email,
                joined_at=stmt.excluded.joined_at,
            ),
        )
        await self.db.execute(stmt)

    async def get_zoom_participant(
        self, *, meeting_id: int, name: str
    ) -> Optional[Mapping]:
        query = zoom_participants.select().where(
            (zoom_participants.c.meeting_id == meeting_id)
            & (zoom_participants.c.name == name)
        )
        return await self.db.fetch_one(query=query)

    async def get_zoom_participants(self, meeting_id: int) -> List[Mapping]:
        return await self.db.fetch_all(
            zoom_participants.select()
            .where(zoom_participants.c.meeting_id == meeting_id)
            .order_by(zoom_participants.c.created_at)
        )

    async def remove_zoom_participant(self, *, meeting_id: int, name: str):
        await self.db.execute(
            zoom_participants.delete().where(
                (zoom_participants.c.meeting_id == meeting_id)
                & (zoom_participants.c.name == name)
            )
        )

    # zzzzoom

    async def create_zzzzoom_meeting(self, *, meeting_id: int):
        created_at = now()
        # TODO: handle id collisions
        stmt = insert(zzzzoom_meetings).values(
            id=generate_nanoid(),
            created_at=created_at,
            meeting_id=meeting_id,
        )
        await self.db.execute(stmt)

    async def get_zzzzoom_meeting(self, id: str):
        query = zzzzoom_meetings.select().where(zzzzoom_meetings.c.id == id)
        return await self.db.fetch_one(query=query)

    async def get_zzzzoom_meeting_for_zoom_meeting(self, meeting_id: int):
        query = zzzzoom_meetings.select().where(
            zzzzoom_meetings.c.meeting_id == meeting_id
        )
        return await self.db.fetch_one(query=query)

    async def zoom_meeting_has_zzzzoom(self, meeting_id: int) -> bool:
        select = sa.select(
            (
                sa.exists()
                .where(zzzzoom_meetings.c.meeting_id == meeting_id)
                .label("result"),
            )
        )
        record = await self.db.fetch_one(select)
        if not record:
            return False
        return record["result"]

    # Topics

    async def save_topics(self, all_topics: Sequence[str]) -> None:
        last_synced_at = now()
        await self.db.execute(topics.delete())
        stmt = insert(topics).values(
            [{"content": topic, "last_synced_at": last_synced_at} for topic in all_topics]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=(topics.c.content,),
            set_=dict(last_synced_at=stmt.excluded.last_synced_at),
        )
        await self.db.execute(stmt)

    async def get_all_topics(self) -> Sequence[str]:
        all_topics = await self.db.fetch_all(topics.select())
        return [record["content"] for record in all_topics]

    # ASLPP

    async def add_aslpp_intro(
        self,
        *,
        message_id: int,
        user_id: int,
        posted_at: dt.datetime,
    ):
        stmt = insert(aslpp_intros).values(
            message_id=message_id,
            user_id=user_id,
            posted_at=posted_at,
            # NOTE: need to pass created_at because `default` doesn't execute
            #  when using postgres's insert
            created_at=now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=(aslpp_intros.c.message_id,),
            set_=dict(
                user_id=stmt.excluded.user_id,
                posted_at=stmt.excluded.posted_at,
                created_at=stmt.excluded.created_at,
            ),
        )
        await self.db.execute(stmt)

    async def clear_aslpp_members(self):
        await self.db.execute(
            aslpp_members.delete().where(aslpp_members.c.is_active == sql.false())
        )

    async def clear_aslpp_intros(self):
        await self.db.execute(aslpp_intros.delete())

    async def add_aslpp_member(
        self,
        *,
        user_id: int,
        joined_at: dt.datetime,
    ):
        stmt = insert(aslpp_members).values(
            user_id=user_id,
            joined_at=joined_at,
            created_at=now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=(aslpp_members.c.user_id,),
            set_=dict(
                joined_at=stmt.excluded.joined_at,
            ),
        )
        await self.db.execute(stmt)

    async def remove_aslpp_member(self, *, user_id: int):
        await self.db.execute(
            aslpp_members.delete().where(aslpp_members.c.user_id == user_id)
        )

    async def get_aslpp_members_without_intro(self, since: dt.timedelta) -> List[Mapping]:
        return await self.db.fetch_all(
            aslpp_members.select()
            .where(
                (aslpp_members.c.is_active == sql.false())
                & (aslpp_members.c.joined_at < (now() - dt.timedelta(days=31)))
            )
            .select_from(
                aslpp_members.outerjoin(
                    aslpp_intros, aslpp_members.c.user_id == aslpp_intros.c.user_id
                )
            )
            .group_by(aslpp_members.c.user_id)
            .having(sa.func.count(aslpp_intros.c.user_id) < 1)
            .order_by(aslpp_members.c.joined_at)
        )

    async def has_aslpp_intro(self, user_id: int) -> bool:
        select = sa.select(
            (sa.exists().where(aslpp_intros.c.user_id == user_id).label("result"),)
        )
        record = await self.db.fetch_one(select)
        if not record:
            return False
        return record["result"]

    async def mark_aslpp_members_active(self, user_ids: List[int]):
        await self.db.execute(
            aslpp_members.update()
            .where(aslpp_members.c.user_id.in_(user_ids))
            .values(is_active=True)
        )

    async def mark_aslpp_members_inactive(self, user_ids: List[int]):
        await self.db.execute(
            aslpp_members.update()
            .where(aslpp_members.c.user_id.in_(user_ids))
            .values(is_active=False)
        )


store = Store(
    database_url=settings.TEST_DATABASE_URL
    if settings.TESTING
    else settings.DATABASE_URL,
    force_rollback=settings.TESTING,
)
