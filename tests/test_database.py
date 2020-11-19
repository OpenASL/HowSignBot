import datetime as dt
import random

import pytest
from freezegun import freeze_time

import database

pytestmark = pytest.mark.asyncio

random.seed(1)


async def test_get_topic_no_guild(store, db):
    await db.execute(database.topics.insert(), {"id": 1, "content": "What's up?"})
    result = await store.get_topic_for_guild()
    assert result == "What's up?"


@freeze_time("2020-09-25 14:00:00")
async def test_get_topic_for_guild(store, db):
    await db.execute(database.topics.insert(), {"id": 1, "content": "What's up?"})
    result = await store.get_topic_for_guild(123)
    assert result == "What's up?"
    usage = await db.fetch_one(
        database.topic_usages.select().where(database.topic_usages.c.topic_id == 1)
    )
    assert usage is not None
    assert usage.get("last_used_at").date() == dt.date(2020, 9, 25)


async def test_get_topic_for_guild_with_used_topic(store, db):
    result = await db.execute_many(
        database.topics.insert(),
        values=(
            {"id": 1, "content": "What's up?"},
            {"id": 2, "content": "Why did you learn ASL?"},
        ),
    )
    await db.execute(
        database.topic_usages.insert(),
        {
            "guild_id": 123,
            "topic_id": 2,
            "last_used_at": dt.datetime(2020, 11, 17, tzinfo=dt.timezone.utc),
        },
    )
    result = await store.get_topic_for_guild(123)
    assert result == "What's up?"


async def test_get_topic_for_guild_with_all_topics_used(store, db):
    result = await db.execute_many(
        database.topics.insert(),
        values=(
            {"id": 1, "content": "What's up?"},
            {"id": 2, "content": "Why did you learn ASL?"},
        ),
    )
    await db.execute_many(
        database.topic_usages.insert(),
        [
            {
                "guild_id": 123,
                "topic_id": 1,
                "last_used_at": dt.datetime(2020, 11, 16, tzinfo=dt.timezone.utc),
            },
            {
                "guild_id": 123,
                "topic_id": 2,
                "last_used_at": dt.datetime(2020, 11, 17, tzinfo=dt.timezone.utc),
            },
        ],
    )
    result = await store.get_topic_for_guild(123)
    assert result == "What's up?"
