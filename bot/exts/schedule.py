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
from disnake import MessageInteraction
from disnake.ext import commands
from disnake.ext.commands import Cog

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
from bot.utils.ui import DropdownView
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


def format_scheduled_start_time(dtime: dt.datetime):
    dtime_pacific = dtime.astimezone(PACIFIC)
    return dtime_pacific.strftime("%A, %B %-d") + " · " + format_multi_time(dtime)


def make_event_embed(event: GuildScheduledEvent) -> disnake.Embed:
    dtime = event.scheduled_start_time
    embed = disnake.Embed(
        title=event.name, description="🗓" + format_scheduled_start_time(dtime)
    )
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
    ) -> tuple[str, disnake.Message]:
        if is_initial_interaction:
            await inter.send(content=prompt)
            prompt_message = await inter.original_message()
        else:
            prompt_message = await inter.channel.send(content=prompt)

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
        response = response_message.content.strip()
        return response, prompt_message

    @commands.slash_command(name="schedule", guild_ids=(settings.ASLPP_GUILD_ID,))
    async def schedule_command(self, inter: GuildCommandInteraction):
        pass

    @schedule_command.sub_command(name="new")
    async def schedule_new(self, inter: GuildCommandInteraction):
        """Add a new scheduled event with guided prompts."""
        # Step 1: Prompt for the start time
        tries = 0
        max_retries = 3
        scheduled_start_time: dt.datetime | None = None
        current_prompt = START_TIME_PROMPT
        while scheduled_start_time is None:
            if tries >= max_retries:
                await inter.send(
                    "⚠️I can't seem to parse your messages. Try running `/schedule new` again and use more specific input.",
                    ephemeral=True,
                )
                return
            start_time, start_time_message = await self._prompt_for_text_input(
                inter,
                prompt=current_prompt,
                is_initial_interaction=tries == 0,
            )
            logger.info(f"attempting to schedule new practice session: {start_time}")
            user_timezone = await store.get_user_timezone(user_id=inter.user.id)
            try:
                scheduled_start_time, used_timezone = parse_practice_time(
                    start_time, user_timezone=user_timezone
                )
            except NoTimeZoneError:
                current_prompt = f'⚠️Could not parse time zone from "{start_time}". Try again. Make sure to include a time zone, e.g. "{PACIFIC_CURRENT_NAME.lower()}".'
            except pytz.UnknownTimeZoneError:
                current_prompt = "⚠️Invalid time zone. Please try again."
            else:
                if not scheduled_start_time:
                    current_prompt = f'⚠️Could not parse "{start_time}" into a date or time. Try again. Make sure to include "am" or "pm" as well as a timezone, e.g. "{PACIFIC_CURRENT_NAME.lower()}".'
                elif scheduled_start_time < utcnow():
                    current_prompt = "⚠Parsed date or time is in the past. Try again with a future date or time."
            tries += 1
        await start_time_message.edit(
            content=(
                "☑️ **When will your event start?**\n"
                f"Entered: {format_scheduled_start_time(scheduled_start_time)}\n"
                "If this is incorrect, enter `cancel` and run `/schedule new` again."
            )
        )

        # Step 2: Prompt for title
        title, title_prompt_message = await self._prompt_for_text_input(
            inter,
            prompt='➡ **Enter a title**, or enter `skip` to use the default ("Practice").',
        )
        await title_prompt_message.edit(
            content=f"☑️ **Enter a title.**\nEntered: {title}",
        )
        if title.lower() == "skip":
            title = "Practice"

        # Step 3: Choosing video service (Zoom or VC)
        guild = inter.guild
        assert inter.user is not None
        user = inter.user
        video_service_view = ButtonGroupView.from_options(
            options=(
                ButtonGroupOption(label="Zoom", value=VideoService.ZOOM, emoji="🟦"),
                ButtonGroupOption(label="VC", value=VideoService.VC, emoji="🔈"),
                ButtonGroupOption(label="Skip", value=VideoService.UNDECIDED),
            ),
            creator_id=user.id,
            choice_label="☑️ **Zoom (recommended) or VC?** Choose one.\nEntered",
        )
        await inter.channel.send(
            "➡ **Zoom (recommended) or VC?** Choose one.", view=video_service_view
        )
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
        await store.create_scheduled_event(event_id=event.id, created_by=user.id)

        event_url = f"https://discord.com/events/{event.guild_id}/{event.id}"
        await inter.channel.send(
            content=(
                '🙌 **Successfully created event.** Click "Event Link" below to mark yourself as "Interested".\n'
                "To cancel your event, use `/schedule cancel`."
            ),
            embed=make_event_embed(event),
            view=LinkView(label="Event Link", url=event_url),
        )

        assert used_timezone is not None
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

    @schedule_command.sub_command(name="cancel")
    async def schedule_cancel(self, inter: GuildCommandInteraction):
        """Cancel an event created through this bot"""
        assert inter.user is not None
        scheduled_events = await store.get_scheduled_events_for_user(inter.user.id)
        events: list[GuildScheduledEvent] = []
        for event in scheduled_events:
            event = inter.guild.get_scheduled_event(event["event_id"])
            if event:
                events.append(event)

        if not events:
            await inter.send("⚠️You have no events cancel.", ephemeral=True)
            return

        await inter.send("👌 OK, let's cancel your event", ephemeral=True)

        async def on_select(select_interaction: MessageInteraction, value: str):
            logger.debug(f"selected event {value}")
            event = inter.guild.get_scheduled_event(int(value))
            assert event is not None
            logger.info(f"canceling event {event.id}")
            await event.delete()
            await select_interaction.response.edit_message(
                content=f'✅ Successfully canceled "{event.name}"',
                view=None,
            )

        options = [
            disnake.SelectOption(
                label=f"{event.name} · {format_scheduled_start_time(event.scheduled_start_time)}",
                value=str(event.id),
            )
            for event in events
        ]
        view = DropdownView.from_options(
            options=options,
            on_select=on_select,
            placeholder="Choose an event",
            creator_id=inter.user.id,
        )
        await inter.send(content="Choose an event to cancel.", view=view, ephemeral=True)

    @Cog.listener()
    async def on_guild_scheduled_event_delete(self, event: GuildScheduledEvent) -> None:
        logger.info(f"removing scheduled event {event.id}")
        await store.remove_scheduled_event(event_id=event.id)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Schedule(bot))
