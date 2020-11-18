#!/usr/bin/env python3
"""Sync database with a Google sheet.

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
TOPICS_SHEET_KEY = env.str("TOPICS_SHEET_KEY", required=True)


async def main():
    client = get_gsheet_client()
    sheet = client.open_by_key(TOPICS_SHEET_KEY)
    worksheet = sheet.get_worksheet(0)
    rows = worksheet.get_all_records()
    all_ids = tuple(row["id"] for row in rows)
    pprint(rows)

    async with Database(DATABASE_URL) as db:
        async with db.transaction():
            stmt = insert(topics).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=(topics.c.id,), set_=dict(content=stmt.excluded.content)
            )
            await db.execute(stmt)
            await db.execute(topics.delete().where(~topics.c.id.in_(all_ids)))
    print(f"Synced {len(rows)} topics.")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
