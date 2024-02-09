import asyncio
import datetime as dt
import logging
import random
from pathlib import Path
from typing import Optional, Tuple, cast

import clthat
import disnake
import handshapes
import holiday_emojis
from disnake.ext.commands import Bot, Cog, Context, command, is_owner

from bot import settings
from bot.database import store
from bot.exts.asl import word_display
from bot.utils.datetimes import (
    EASTERN,
    PACIFIC,
    format_datetime,
    parse_human_readable_datetime,
    utcnow,
)
from bot.utils.discord import THEME_COLOR, get_event_url
from bot.utils.tasks import daily_task

from ._practice_sessions import (
    get_practice_sessions,
    make_base_embed,
    make_practice_session_embed,
)

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX
HERE = Path(__file__).parent


def get_today_random(dtime: Optional[dt.datetime] = None) -> random.Random:
    dtime = dtime or utcnow()
    seed = settings.DAILY_MESSAGE_RANDOM_SEED or dtime.date().toordinal()
    return random.Random(seed)


RANDOMIZED_HANDSHAPE_NAMES = list(handshapes.HANDSHAPE_NAMES)
random.Random("handshapes").shuffle(RANDOMIZED_HANDSHAPE_NAMES)


def get_daily_handshape(dtime: Optional[dt.datetime] = None) -> handshapes.Handshape:
    dtime = dtime or utcnow()
    day_of_year = dtime.timetuple().tm_yday
    name = RANDOMIZED_HANDSHAPE_NAMES[day_of_year % len(RANDOMIZED_HANDSHAPE_NAMES)]
    return handshapes.get_handshape(name)


async def get_daily_topics(dtime: Optional[dt.datetime] = None) -> Tuple[str, str]:
    topics = await store.get_all_topics()
    rand = get_today_random(dtime)
    return (rand.choice(topics), rand.choice(topics))


def get_daily_clthat(dtime: Optional[dt.datetime] = None) -> str:
    return clthat.text(get_today_random(dtime))


TOPIC_DAYS = {0, 2, 4, 6}  # M W F Su
CLTHAT_DAYS = {1, 3, 5}  # Tu Th Sa


class DailyMessage(Cog, name="Daily Message"):  # type: ignore
    def __init__(self, bot: Bot):
        self.bot = bot

    @Cog.listener()
    async def on_ready(self):
        self.bot.loop.create_task(self.daily_message())

    @command(
        name="send_daily_message",
        aliases=("sdm",),
        hidden=True,
        help="BOT OWNER ONLY: Manually send a daily practice schedule for a channel",
    )
    @is_owner()
    async def send_daily_message_command(
        self,
        ctx: Context,
        channel: Optional[disnake.TextChannel] = None,
        when: Optional[str] = None,
    ):
        await ctx.channel.trigger_typing()
        channel_id = channel.id if channel else ctx.channel.id
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
            channel = cast(disnake.TextChannel, self.bot.get_channel(channel_id))
            guild = channel.guild
            await ctx.send(f'🗓 Daily message sent to "{guild.name}", #{channel.name}')

    async def send_daily_message(
        self, channel_id: int, dtime: Optional[dt.datetime] = None
    ):
        channel = cast(disnake.TextChannel, self.bot.get_channel(channel_id))
        guild = channel.guild
        logger.info(f'sending daily message for guild: "{guild.name}" in #{channel.name}')
        guild_id = guild.id
        dtime = dtime or utcnow()
        prefer_dates_from = (
            "current_period" if dtime.date() <= dt.date.today() else "future"
        )
        parse_settings = {"PREFER_DATES_FROM": prefer_dates_from}
        settings = await store.get_guild_settings(guild.id)
        if not settings:
            return
        embed: disnake.Embed
        if settings["include_practice_schedule"]:
            sessions = await get_practice_sessions(
                guild_id,
                dtime=dtime,
                parse_settings=parse_settings,
            )
            embed = await make_practice_session_embed(guild_id, sessions, dtime=dtime)
        else:
            embed = make_base_embed(dtime=dtime)

        if settings["include_scheduled_events"]:
            # Display scheduled events for today
            events = await guild.fetch_scheduled_events()
            events_today = sorted(
                (
                    event
                    for event in events
                    if (
                        event.scheduled_start_time.astimezone(PACIFIC).date()
                        == dtime.astimezone(PACIFIC).date()
                    )
                ),
                key=lambda event: event.scheduled_start_time,
            )
            for event in events_today:
                embed.add_field(
                    name=format_datetime(event.scheduled_start_time, format_type="t"),
                    value=f"{event.name} · [Details/RSVP]({get_event_url(event)})",
                    inline=False,
                )

        announcements = await store.get_guild_announcements(guild.id)
        for announcement in announcements:
            embed.add_field(
                name=announcement["title"],
                value=f"> {announcement['description']}",
                inline=False,
            )

        send_kwargs = {}
        include_handshape_of_the_day = settings["include_handshape_of_the_day"]
        handshape = None
        holiday = holiday_emojis.get(dtime.date())
        if holiday and holiday.term is not None:
            embed.add_field(
                name=holiday.term.upper(),
                value=word_display(holiday.term),
                inline=False,
            )
        elif include_handshape_of_the_day:
            # Handshape of the Day
            handshape = get_daily_handshape(dtime)
            filename = f"{handshape.name}.png"
            send_kwargs["file"] = disnake.File(handshape.path, filename=filename)
            embed.set_thumbnail(url=f"attachment://{filename}")
            embed.add_field(
                name="Handshape of the Day", value=f'"{handshape.name}"', inline=False
            )

        if not holiday:
            # Topics of the Day
            weekday = dtime.weekday()
            if settings.get("include_topics_of_the_day") and weekday in TOPIC_DAYS:
                topic, topic2 = await get_daily_topics(dtime)
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

        message = await channel.send(embed=embed, **send_kwargs)
        if include_handshape_of_the_day and handshape:
            await message.create_thread(
                name=f"What signs use the {handshape.name} handshape?",
                auto_archive_duration=disnake.ThreadArchiveDuration.day,
            )
        include_wordle = settings["include_wordle"]
        if include_wordle:
            wordle_embed = disnake.Embed(
                title="Daily ASL Wordle",
                description="https://dactle.sloria.io/",
                color=THEME_COLOR,
            )
            wordle_embed.set_thumbnail(url="attachment://wordle.png")
            wordle_message = await channel.send(
                embed=wordle_embed,
                file=disnake.File(HERE / "wordle.png", filename="wordle.png"),
            )
            epoch = dt.datetime(2022, 1, 26, tzinfo=EASTERN)
            wordle_num = (dtime - epoch).days
            await wordle_message.create_thread(
                name=f"Wordle {wordle_num}",
                auto_archive_duration=disnake.ThreadArchiveDuration.day,
            )

    async def daily_message(self):
        async with daily_task(
            settings.DAILY_PRACTICE_SEND_TIME, name="daily message send"
        ):
            channel_ids = list(await store.get_daily_message_channel_ids())
            for channel_id in channel_ids:
                try:
                    asyncio.create_task(self.send_daily_message(channel_id))
                except Exception:
                    logger.exception(f"could not send to channel {channel_id}")


def setup(bot: Bot) -> None:
    bot.add_cog(DailyMessage(bot))
