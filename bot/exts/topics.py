import datetime as dt
import logging
import random

import discord
from aiohttp import web
from discord.ext.commands import Bot
from discord.ext.commands import Cog
from discord.ext.commands import command
from discord.ext.commands import Context
from discord.ext.commands import is_owner

from bot import settings
from bot.database import store
from bot.utils.datetimes import EASTERN
from bot.utils.datetimes import utcnow
from bot.utils.gsheets import get_gsheet_client

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------

DAILY_SYNC_TIME = dt.time(7, 0)  # Eastern time


class Topics(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @Cog.listener()
    async def on_ready(self):
        self.bot.loop.create_task(self.daily_sync())

    @command(
        name="synctopics",
        aliases=("st",),
        hidden=True,
    )
    @is_owner()
    async def sync_topics_command(self, ctx: Context):
        await ctx.channel.trigger_typing()
        topics = await sync_topics()
        await ctx.reply(f"✅ Synced {len(topics)} topics.")

    async def daily_sync(self):
        while True:
            now_eastern = dt.datetime.now(EASTERN)
            date = now_eastern.date()
            if now_eastern.time() > DAILY_SYNC_TIME:
                date = now_eastern.date() + dt.timedelta(days=1)
            then = EASTERN.localize(dt.datetime.combine(date, DAILY_SYNC_TIME))
            logger.info(f"topics will be synced at at {then.isoformat()}")
            await discord.utils.sleep_until(then.astimezone(dt.timezone.utc))
            topics = await sync_topics()
            logger.info(f"synced {len(topics)} topics")


# -----------------------------------------------------------------------------


async def sync_topics():
    topics = get_gsheet_topics()
    async with store.transaction():
        await store.save_topics(topics)
    return topics


def get_gsheet_topics():
    client = get_gsheet_client()
    sheet = client.open_by_key(settings.TOPICS_SHEET_KEY)
    worksheet = sheet.get_worksheet(0)
    return [each["content"] for each in worksheet.get_all_records()]


def floor_minute(d: dt.datetime):
    return d - dt.timedelta(seconds=d.second, microseconds=d.microsecond)


def get_minute_random(seed=None):
    dtime = floor_minute(utcnow())
    s = dtime.isoformat()
    if seed:
        s += str(seed)
    return random.Random(s)


# -----------------------------------------------------------------------------


async def totm(request):
    topics = await store.get_all_topics()

    seed = request.query.get("s")
    rand = get_minute_random(seed)
    topic = rand.choice(topics)
    return web.Response(body=topic, status=200)


# -----------------------------------------------------------------------------


def setup(bot: Bot) -> None:
    cors = bot.app.cors
    resource = bot.app.router.add_resource("/totm")
    resource.add_route("GET", totm)
    cors.add(resource)

    bot.add_cog(Topics(bot))
