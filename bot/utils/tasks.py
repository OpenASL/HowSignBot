from __future__ import annotations

import datetime as dt
import logging
from contextlib import asynccontextmanager

import disnake

from .datetimes import EASTERN

logger = logging.getLogger(__name__)


def get_next_task_execution_datetime(time_in_eastern: dt.time) -> dt.datetime:
    """Get next execution time for a daily task.

    Returns an eastern-localized datetime.
    """
    now_eastern = dt.datetime.now(EASTERN)
    date = now_eastern.date()
    if now_eastern.time() > time_in_eastern:
        date = now_eastern.date() + dt.timedelta(days=1)
    return EASTERN.localize(dt.datetime.combine(date, time_in_eastern))


@asynccontextmanager
async def daily_task(time_in_eastern: dt.time, *, name: str):
    """Async context manager that executes its block on a daily basis."""
    while True:
        next_execution_time = get_next_task_execution_datetime(time_in_eastern)
        logger.info(f"{name} will be executed at at {next_execution_time.isoformat()}")
        await disnake.utils.sleep_until(next_execution_time.astimezone(dt.timezone.utc))
        yield
        logger.info(f"executed {name}")
