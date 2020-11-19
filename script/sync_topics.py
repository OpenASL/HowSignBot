#!/usr/bin/env python3
"""Sync database with a Google sheet.
This should be run locally.

Usage: PYTHONPATH=. ./script/sync_topics.py
"""
import asyncio
from pprint import pprint

from environs import Env

from databases import Database
from database import topics
from sqlalchemy.dialects.postgresql import insert

from bot import get_gsheet_client

env = Env()
env.read_env()

DATABASE_URL = env.str("DATABASE_URL", required=True)
STAGING_DATABASE_URL = env.str("STAGING_DATABASE_URL", None)
PROD_DATABASE_URL = env.str("PROD_DATABASE_URL", None)
TOPICS_SHEET_KEY = env.str("TOPICS_SHEET_KEY", required=True)


async def sync_topics(database_url, rows):
    all_ids = tuple(row["id"] for row in rows)
    async with Database(database_url) as db:
        async with db.transaction():
            stmt = insert(topics).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=(topics.c.id,), set_=dict(content=stmt.excluded.content)
            )
            await db.execute(stmt)
            await db.execute(topics.delete().where(~topics.c.id.in_(all_ids)))


async def main():
    client = get_gsheet_client()
    sheet = client.open_by_key(TOPICS_SHEET_KEY)
    worksheet = sheet.get_worksheet(0)
    rows = worksheet.get_all_records()
    pprint(rows)

    for database_url in (DATABASE_URL, STAGING_DATABASE_URL, PROD_DATABASE_URL):
        if database_url:
            await sync_topics(database_url, rows)

    print(f"Synced {len(rows)} topics.")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
