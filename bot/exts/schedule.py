from __future__ import annotations

import asyncio
import datetime as dt
import logging
from enum import auto
from enum import Enum
from typing import Any

import disnake
import pytz
from disnake import GuildCommandInteraction
from disnake import GuildScheduledEvent
from disnake.ext import commands

from bot import settings
from bot.database import store
from bot.exts.practices.practice import parse_practice_time
from bot.utils.datetimes import display_timezone
from bot.utils.datetimes import EASTERN_CURRENT_NAME
from bot.utils.datetimes import format_multi_time
from bot.utils.datetimes import NoTimeZoneError
from bot.utils.datetimes import PACIFIC
from bot.utils.datetimes import PACIFIC_CURRENT_NAME
from bot.utils.datetimes import utcnow
from bot.utils.discord import display_name
from bot.utils.ui import ButtonGroupOption
from bot.utils.ui import ButtonGroupView
from bot.utils.ui import LinkView

logger = logging.getLogger(__name__)

TIMEZONE_CHANGE_TEMPLATE = """🙌 Thanks for scheduling a practice! I'll remember your time zone (**{new_timezone}**) so you don't need to include a time zone when scheduling future practices.
Before: `tomorrow 8pm {new_timezone_display}`
After: `tomorrow 8pm`
"""

START_TIME_PROMPT = """➡ **When will your event start?**
Examples:
```
today 2pm {pacific}
tomorrow 5pm {eastern}
saturday 6pm {pacific}
9/24 6pm {eastern}
```
Or enter `cancel` to cancel.
""".format(
    pacific=PACIFIC_CURRENT_NAME.lower(), eastern=EASTERN_CURRENT_NAME.lower()
)


class VideoService(Enum):
    ZOOM = auto()
    VC = auto()
    UNDECIDED = auto()


class PromptCancelled(Exception):
    pass


def make_event_embed(event: GuildScheduledEvent) -> disnake.Embed:
    dtime = event.scheduled_start_time
    dtime_pacific = dtime.astimezone(PACIFIC)
    description = (
        "🗓 " + dtime_pacific.strftime("%A, %B %-d") + " · " + format_multi_time(dtime)
    )
    embed = disnake.Embed(title=event.name, description=description)
    return embed


class Schedule(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _prompt_for_text_input(
        self,
        inter: GuildCommandInteraction,
        *,
        prompt: str,
        is_initial_interaction: bool = False,
    ) -> str:
        if is_initial_interaction:
            await inter.send(content=prompt)
        else:
            await inter.channel.send(content=prompt)

        def check_user_response(m: disnake.Message):
            return m.author == inter.user and m.channel.id == m.channel.id

        try:
            response_message: disnake.Message = await self.bot.wait_for(
                "message",
                check=check_user_response,
                timeout=60,
            )
        except asyncio.exceptions.TimeoutError:
            await inter.send(content="⚠️ You waited too long to respond. Try again.")
            raise PromptCancelled
        if response_message.content.lower() == "cancel":
            await response_message.reply(content="✨ _Cancelled_")
            raise PromptCancelled
        return response_message.content.strip()

    @commands.slash_command(name="schedule", guild_ids=(settings.ASLPP_GUILD_ID,))
    async def schedule_command(self, inter: GuildCommandInteraction):
        pass

    @schedule_command.sub_command(name="new")
    async def schedule_new(self, inter: GuildCommandInteraction):
        """Quickly add a new scheduled event with guided prompts."""
        # Step 1: Prompt for the start time
        start_time = await self._prompt_for_text_input(
            inter, prompt=START_TIME_PROMPT, is_initial_interaction=True
        )
        logger.info(f"attempting to schedule new practice session: {start_time}")
        user_timezone = await store.get_user_timezone(user_id=inter.user.id)
        try:
            scheduled_start_time, used_timezone = parse_practice_time(
                start_time, user_timezone=user_timezone
            )
        except NoTimeZoneError:
            raise commands.errors.BadArgument(
                f'⚠️Could not parse time zone from "{start_time}". Make sure to include a time zone, e.g. "{PACIFIC_CURRENT_NAME.lower()}".'
            )
        except pytz.UnknownTimeZoneError:
            raise commands.errors.BadArgument("⚠️Invalid time zone. Please try again.")
        if not scheduled_start_time:
            raise commands.errors.BadArgument(
                f'⚠️Could not parse "{start_time}" into a date or time. Make sure to include "am" or "pm" as well as a timezone, e.g. "{PACIFIC_CURRENT_NAME.lower()}".'
            )
        assert used_timezone is not None
        if scheduled_start_time < utcnow():
            raise commands.errors.BadArgument(
                "⚠Parsed date or time is in the past. Try again with a future date or time."
            )

        # Step 2: Prompt for title
        title = await self._prompt_for_text_input(
            inter, prompt="➡ **Enter a title**, or enter `skip` to use the default."
        )
        if title.lower() == "skip":
            title = "Practice"

        guild = inter.guild
        # Step 3: Choosing video service (Zoom or VC)
        assert inter.user is not None
        user = inter.user
        video_service_view = ButtonGroupView.from_options(
            options=(
                ButtonGroupOption(
                    label="Zoom (recommended)", value=VideoService.ZOOM, emoji="🟦"
                ),
                ButtonGroupOption(label="VC", value=VideoService.VC, emoji="🔈"),
                ButtonGroupOption(label="Skip", value=VideoService.UNDECIDED),
            ),
            creator_id=user.id,
        )
        await inter.channel.send("➡ **Zoom or VC?** Choose one.", view=video_service_view)
        video_service_value: VideoService | None = (
            await video_service_view.wait_for_value()
        )
        if video_service_value is None:
            video_service_value = VideoService.UNDECIDED

        video_service_kwargs: dict[str, Any] = {}
        if video_service_value == VideoService.ZOOM:
            video_service_kwargs = dict(
                entity_type=disnake.GuildScheduledEventEntityType.external,
                entity_metadata=disnake.GuildScheduledEventMetadata(
                    location="Zoom will be posted in practice channel"
                ),
            )
        elif video_service_value == VideoService.VC:
            voice_channel = guild.voice_channels[0]
            video_service_kwargs = dict(
                entity_type=disnake.GuildScheduledEventEntityType.voice,
                channel_id=voice_channel.id,
            )
        else:  # UNDECIDED
            video_service_kwargs = dict(
                entity_type=disnake.GuildScheduledEventEntityType.external,
                entity_metadata=disnake.GuildScheduledEventMetadata(location="TBD"),
            )

        scheduled_end_time = scheduled_start_time + dt.timedelta(hours=1)

        event = await guild.create_scheduled_event(
            name=title,
            description=f"Host: {user.mention}\n_Created with_ `/schedule new`",
            scheduled_start_time=scheduled_start_time,
            scheduled_end_time=scheduled_end_time,
            reason=f"/schedule command used by user {user.id} ({display_name(user)})",
            **video_service_kwargs,
        )

        event_url = f"https://discord.com/events/{event.guild_id}/{event.id}"
        await inter.channel.send(
            content='🙌 **Successfully created event.** Click "Event Link" below to view or edit your event.',
            embed=make_event_embed(event),
            view=LinkView(label="Event Link", url=event_url),
        )
        if str(user_timezone) != str(used_timezone):
            await store.set_user_timezone(user.id, used_timezone)
            new_timezone_display = display_timezone(used_timezone, utcnow()).lower()
            dm_response = TIMEZONE_CHANGE_TEMPLATE.format(
                new_timezone=used_timezone,
                new_timezone_display=new_timezone_display,
            )
            try:
                await user.send(dm_response)
            except disnake.errors.Forbidden:
                logger.warn("cannot send DM to user. skipping...")


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Schedule(bot))
