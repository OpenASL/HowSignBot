import asyncio
import datetime as dt
import logging
import random
from typing import Optional
from typing import Tuple

import discord
from discord.ext.commands import Bot
from discord.ext.commands import Cog
from discord.ext.commands import command
from discord.ext.commands import Context
from discord.ext.commands import is_owner

import clthat
import handshapes
import holiday_emojis
from ._practice_sessions import get_practice_sessions
from ._practice_sessions import make_practice_session_embed
from bot import settings
from bot.database import store
from bot.exts.asl import word_display
from bot.utils.datetimes import EASTERN
from bot.utils.datetimes import parse_human_readable_datetime
from bot.utils.datetimes import utcnow
from bot.utils.gsheets import get_gsheet_client

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX


def get_today_random(dtime: Optional[dt.datetime] = None) -> random.Random:
    dtime = dtime or utcnow()
    seed = settings.DAILY_MESSAGE_RANDOM_SEED or dtime.date().toordinal()
    return random.Random(seed)


def get_daily_handshape(dtime: Optional[dt.datetime] = None) -> handshapes.Handshape:
    return handshapes.get_random_handshape(get_today_random(dtime))


def get_daily_topics(dtime: Optional[dt.datetime] = None) -> Tuple[str, str]:
    client = get_gsheet_client()
    sheet = client.open_by_key(settings.TOPICS_SHEET_KEY)
    worksheet = sheet.get_worksheet(0)
    rows = worksheet.get_all_records()

    rand = get_today_random(dtime)

    return (rand.choice(rows)["content"], rand.choice(rows)["content"])


def get_daily_clthat(dtime: Optional[dt.datetime] = None) -> str:
    return clthat.text(get_today_random(dtime))


TOPIC_DAYS = {0, 2, 4, 6}  # M W F Su
CLTHAT_DAYS = {1, 3, 5}  # Tu Th Sa


class DailyMessage(Cog, name="Daily Message"):  # type: ignore
    def __init__(self, bot: Bot):
        self.bot = bot

    @Cog.listener()
    async def on_ready(self):
        self.bot.loop.create_task(self.daily_practice_message())

    @command(
        name="send_daily_message",
        aliases=("sdm",),
        hidden=True,
        help="BOT OWNER ONLY: Manually send a daily practice schedule for a channel",
    )
    @is_owner()
    async def send_daily_message_command(
        self, ctx: Context, channel_id: Optional[int] = None, when: Optional[str] = None
    ):
        await ctx.channel.trigger_typing()
        channel_id = channel_id or ctx.channel.id
        channel_ids = set(await store.get_daily_message_channel_ids())
        if channel_id not in channel_ids:
            await ctx.send(
                f"⚠️ Schedule channel not configured for Channel ID {channel_id}"
            )
            return
        dtime = (
            parse_human_readable_datetime(
                when, settings={"PREFER_DATES_FROM": "future"}, user_timezone=EASTERN
            )[0]
            if when
            else utcnow().astimezone(EASTERN)
        )
        assert dtime is not None
        send_dtime = EASTERN.localize(
            dt.datetime.combine(dtime, settings.DAILY_PRACTICE_SEND_TIME)
        )
        await self.send_daily_message(channel_id, send_dtime)

        if channel_id != ctx.channel.id:
            channel = self.bot.get_channel(channel_id)
            guild = channel.guild
            await ctx.send(f'🗓 Daily message sent to "{guild.name}", #{channel.name}')

    async def send_daily_message(
        self, channel_id: int, dtime: Optional[dt.datetime] = None
    ):
        channel = self.bot.get_channel(channel_id)
        guild = channel.guild
        logger.info(f'sending daily message for guild: "{guild.name}" in #{channel.name}')
        guild_id = guild.id
        dtime = dtime or utcnow()
        sessions = await get_practice_sessions(guild_id, dtime=dtime)
        embed = await make_practice_session_embed(guild_id, sessions, dtime=dtime)
        file_ = None

        settings = await store.get_guild_settings(guild.id)
        if not settings:
            return

        holiday = holiday_emojis.get(dtime.date())
        if holiday and holiday.term is not None:
            embed.add_field(
                name=holiday.term.upper(),
                value=word_display(holiday.term),
                inline=False,
            )
        elif settings.get("include_handshape_of_the_day"):
            # Handshape of the Day
            handshape = get_daily_handshape(dtime)
            filename = f"{handshape.name}.png"
            file_ = discord.File(handshape.path, filename=filename)
            embed.set_thumbnail(url=f"attachment://{filename}")
            embed.add_field(
                name="Handshape of the Day", value=f'"{handshape.name}"', inline=False
            )

        if not holiday:
            # Topics of the Day
            weekday = dtime.weekday()
            if settings.get("include_topics_of_the_day") and weekday in TOPIC_DAYS:
                topic, topic2 = get_daily_topics(dtime)
                embed.add_field(
                    name="Discuss...", value=f'"{topic}"\n\n"{topic2}"', inline=False
                )

            # CL That
            if settings.get("include_clthat") and weekday in CLTHAT_DAYS:
                embed.add_field(
                    name="CL That!",
                    value=f'How would you sign: "{get_daily_clthat(dtime)}"',
                    inline=False,
                )

        await channel.send(file=file_, embed=embed)

    async def daily_practice_message(self):
        while True:
            # DAILY_PRACTICE_SEND_TIME is defined in Eastern time
            now_eastern = dt.datetime.now(EASTERN)
            date = now_eastern.date()
            if now_eastern.time() > settings.DAILY_PRACTICE_SEND_TIME:
                date = now_eastern.date() + dt.timedelta(days=1)
            then = EASTERN.localize(
                dt.datetime.combine(date, settings.DAILY_PRACTICE_SEND_TIME)
            )
            channel_ids = list(await store.get_daily_message_channel_ids())
            logger.info(
                f"practice schedules for {len(channel_ids)} channels will be sent at {then.isoformat()}"
            )
            await discord.utils.sleep_until(then.astimezone(dt.timezone.utc))
            for channel_id in channel_ids:
                try:
                    asyncio.create_task(self.send_daily_message(channel_id))
                except Exception:
                    logger.exception(f"could not send to channel {channel_id}")


def setup(bot: Bot) -> None:
    bot.add_cog(DailyMessage(bot))
