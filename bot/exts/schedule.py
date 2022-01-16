from __future__ import annotations

import asyncio
import datetime as dt
import logging
from enum import Enum, auto
from typing import Any

import disnake
import pytz
from disnake import GuildCommandInteraction, GuildScheduledEvent, MessageInteraction
from disnake.ext import commands
from disnake.ext.commands import Cog
from pytz.tzinfo import StaticTzInfo

from bot import settings
from bot.database import store
from bot.exts.practices.practice import parse_practice_time
from bot.utils import truncate
from bot.utils.datetimes import (
    EASTERN_CURRENT_NAME,
    PACIFIC,
    PACIFIC_CURRENT_NAME,
    NoTimeZoneError,
    display_timezone,
    format_multi_time,
    utcnow,
)
from bot.utils.discord import display_name
from bot.utils.ui import ButtonGroupOption, ButtonGroupView, DropdownView

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


class MaxPromptAttemptsExceeded(Exception):
    pass


def format_scheduled_start_time(dtime: dt.datetime):
    dtime_pacific = dtime.astimezone(PACIFIC)
    return dtime_pacific.strftime("%A, %B %-d") + " · " + format_multi_time(dtime)


def get_event_url(event: GuildScheduledEvent) -> str:
    return f"https://discord.com/events/{event.guild_id}/{event.id}"


def get_event_label(event: GuildScheduledEvent, bold: bool = False) -> str:
    formatted_time = format_scheduled_start_time(event.scheduled_start_time)
    truncated_event_name = truncate(event.name, max_len=100 - len(formatted_time) - 4)
    event_name = f"**{truncated_event_name}**" if bold else truncated_event_name
    return f"{event_name} · {formatted_time}"


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
                timeout=120,
            )
        except asyncio.exceptions.TimeoutError:
            await inter.send(
                content="⚠️ You waited too long to respond. Try running `/schedule …` again."
            )
            # TODO: handle this error more gracefully so it doesn't pollute the logs
            raise PromptCancelled
        if response_message.content.lower() == "cancel":
            await response_message.reply(content="✨ _Cancelled_")
            raise PromptCancelled
        response = response_message.content.strip()
        return response, prompt_message

    @commands.slash_command(name="schedule", guild_ids=(settings.SIGN_CAFE_GUILD_ID,))
    async def schedule_command(self, inter: GuildCommandInteraction):
        pass

    @schedule_command.sub_command(name="new")
    async def schedule_new(self, inter: GuildCommandInteraction):
        """Add a new scheduled event with guided prompts."""
        # Step 1: Prompt for the start time
        try:
            scheduled_start_time, used_timezone = await self._prompt_for_start_time(inter)
        except MaxPromptAttemptsExceeded:
            await inter.send(
                "⚠️I can't seem to parse your messages. Try running `/schedule new` again and use more specific input.",
                ephemeral=True,
            )
            return
        if scheduled_start_time < utcnow():
            await inter.send(
                "⚠️ Can't schedule an event in the past. Try running `/schedule new` again and use a more specific input."
            )
            return

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
        video_service_kwargs = await self._prompt_for_video_service(
            inter, user=user, guild=guild
        )

        scheduled_end_time = scheduled_start_time + dt.timedelta(hours=1)

        event = await guild.create_scheduled_event(
            name=title,
            description=f"Host: {display_name(user)} ({user.mention})\n_Created with_ `/schedule new`",
            scheduled_start_time=scheduled_start_time,
            scheduled_end_time=scheduled_end_time,
            reason=f"/schedule command used by user {user.id} ({display_name(user)})",
            **video_service_kwargs,
        )
        await store.create_scheduled_event(event_id=event.id, created_by=user.id)

        await inter.channel.send(
            content=(
                '🙌 **Successfully created event.** Mark yourself as "Interested" below.\n'
                "To edit your event, use `/schedule edit …`.\n"
                "To cancel your event, use `/schedule cancel`.\n" + get_event_url(event)
            ),
        )

        assert used_timezone is not None
        await self._store_and_notify_for_user_timezone_change(
            user=inter.user,
            used_timezone=used_timezone,
        )

    @schedule_command.sub_command(name="cancel")
    async def schedule_cancel(self, inter: GuildCommandInteraction):
        """Cancel an event created through this bot"""
        assert inter.user is not None
        events = await self._get_events_for_user(user_id=inter.user.id, guild=inter.guild)
        if not events:
            await inter.send("⚠️You have no events to cancel.", ephemeral=True)
            return

        await inter.send("👌 OK, let's cancel your event.")

        async def on_select(select_interaction: MessageInteraction, value: str):
            logger.debug(f"selected event {value}")
            event = inter.guild.get_scheduled_event(int(value))
            assert event is not None
            logger.info(f"canceling event {event.id}")
            await event.delete()
            await select_interaction.response.edit_message(
                content=f"🙌 Successfully cancelled **{event.name}**.",
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
        await inter.send(content="Choose an event to cancel.", view=view)

    @schedule_command.sub_command_group(name="edit")
    async def schedule_edit(self, inter: GuildCommandInteraction):
        """Edit a scheduled event"""
        pass

    @schedule_edit.sub_command(name="name")
    async def schedule_edit_name(self, inter: GuildCommandInteraction):
        """Edit a scheduled event's name"""
        assert inter.user is not None
        events = await self._get_events_for_user(user_id=inter.user.id, guild=inter.guild)
        if not events:
            await inter.send("⚠️You have no events to edit.", ephemeral=True)
            return

        await inter.send("👌 OK, let's edit your event's name.")

        async def on_select(select_interaction: MessageInteraction, value: str):
            logger.debug(f"selected event {value}")
            event = inter.guild.get_scheduled_event(int(value))
            assert event is not None
            logger.info(f"editing event title for event {event.id}")
            await select_interaction.response.edit_message(
                content=f"☑️ Editing: **{event.name}**",
                view=None,
            )
            prompt_content = "➡ What would you like the new name to be?"
            name, prompt_message = await self._prompt_for_text_input(
                inter,
                prompt=prompt_content,
            )
            await prompt_message.edit(content=prompt_content.replace("➡", "☑️"))
            event = await event.edit(name=name)
            await inter.send(
                content=f"🙌 Successfully edited event name to: **{name}**.\n"
                + get_event_url(event),
            )

        options = [
            disnake.SelectOption(
                label=get_event_label(event),
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
        await inter.send(content="Choose an event to edit.", view=view)

    @schedule_edit.sub_command(name="time")
    async def schedule_edit_time(self, inter: GuildCommandInteraction):
        """Edit a scheduled event's time"""
        assert inter.user is not None
        events = await self._get_events_for_user(user_id=inter.user.id, guild=inter.guild)
        if not events:
            await inter.send("⚠️You have no events to edit.", ephemeral=True)
            return

        await inter.send("👌 OK, let's edit your event's time.")

        async def on_select(select_interaction: MessageInteraction, value: str):
            logger.debug(f"selected event {value}")
            event = inter.guild.get_scheduled_event(int(value))
            assert event is not None
            await select_interaction.response.edit_message(
                content=f"☑️ Editing: {get_event_label(event, bold=True)}",
                view=None,
            )

            if event.scheduled_end_time:
                duration = event.scheduled_end_time - event.scheduled_start_time
            else:
                duration = dt.timedelta(hours=1)

            try:
                scheduled_start_time, used_timezone = await self._prompt_for_start_time(
                    inter, is_initial_interaction=False
                )
            except MaxPromptAttemptsExceeded:
                await inter.send(
                    "⚠️I can't seem to parse your messages. Try running `/schedule edit time` again and use more specific input.",
                    ephemeral=True,
                )
                return

            scheduled_end_time = scheduled_start_time + duration
            logger.info(f"editing event start and end time for event {event.id}")
            event = await event.edit(
                scheduled_start_time=scheduled_start_time,
                scheduled_end_time=scheduled_end_time,
            )
            assert event is not None
            await inter.send(
                content="🙌 Successfully edited event time.\n" + get_event_url(event),
            )
            assert used_timezone is not None
            await self._store_and_notify_for_user_timezone_change(
                user=inter.user,
                used_timezone=used_timezone,
            )

        options = [
            disnake.SelectOption(
                label=get_event_label(event),
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
        await inter.send(content="Choose an event to edit.", view=view)

    @schedule_edit.sub_command(name="video")
    async def schedule_edit_video(self, inter: GuildCommandInteraction):
        """Edit a scheduled event's video service (Zoom or VC)"""
        assert inter.user is not None
        events = await self._get_events_for_user(user_id=inter.user.id, guild=inter.guild)
        if not events:
            await inter.send("⚠️You have no events to edit.", ephemeral=True)
            return

        await inter.send("👌 OK, let's edit your event's video service.")

        async def on_select(select_interaction: MessageInteraction, value: str):
            logger.debug(f"selected event {value}")
            event = inter.guild.get_scheduled_event(int(value))
            assert event is not None
            logger.info(f"editing event title for event {event.id}")
            await select_interaction.response.edit_message(
                content=f"☑️ Editing: {get_event_label(event, bold=True)}",
                view=None,
            )

            assert inter.user is not None
            video_service_kwargs = await self._prompt_for_video_service(
                inter, user=inter.user, guild=inter.guild
            )
            scheduled_end_time = (
                event.scheduled_end_time
                if event.scheduled_end_time
                else event.scheduled_start_time + dt.timedelta(hours=1)
            )
            event = await event.edit(
                # XXX API requires passing scheduled end time for some reason
                scheduled_start_time=event.scheduled_start_time,
                scheduled_end_time=scheduled_end_time,
                **video_service_kwargs,
            )
            assert event is not None

            await inter.send(
                content="🙌 Successfully edited video service.\n" + get_event_url(event)
            )

        options = [
            disnake.SelectOption(
                label=get_event_label(event),
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
        await inter.send(content="Choose an event to edit.", view=view)

    @Cog.listener()
    async def on_guild_scheduled_event_delete(self, event: GuildScheduledEvent) -> None:
        logger.info(f"removing scheduled event {event.id}")
        await store.remove_scheduled_event(event_id=event.id)

    async def _get_events_for_user(
        self, user_id: int, *, guild: disnake.Guild
    ) -> list[GuildScheduledEvent]:
        scheduled_events = await store.get_scheduled_events_for_user(user_id)
        events: list[GuildScheduledEvent] = []
        for event in scheduled_events:
            event = guild.get_scheduled_event(event["event_id"])
            if event:
                events.append(event)
        return sorted(events, key=lambda e: e.scheduled_start_time)

    async def _prompt_for_start_time(
        self,
        inter: GuildCommandInteraction,
        is_initial_interaction: bool | None = None,
    ) -> tuple[dt.datetime, StaticTzInfo | None]:
        tries = 0
        max_retries = 3
        scheduled_start_time: dt.datetime | None = None
        current_prompt = START_TIME_PROMPT
        used_timezone: StaticTzInfo | None = None
        start_time_message: disnake.Message | None = None
        while scheduled_start_time is None:
            if tries >= max_retries:
                raise MaxPromptAttemptsExceeded

            start_time, start_time_message = await self._prompt_for_text_input(
                inter,
                prompt=current_prompt,
                is_initial_interaction=(
                    is_initial_interaction
                    if is_initial_interaction is not None
                    else tries == 0
                ),
            )
            logger.info(f"attempting to schedule new practice session: {start_time}")
            assert inter.user is not None
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
        assert start_time_message is not None
        await start_time_message.edit(
            content=(
                "☑️ **When will your event start?**\n"
                f"Entered: {format_scheduled_start_time(scheduled_start_time)}"
            )
        )
        return scheduled_start_time, used_timezone

    async def _store_and_notify_for_user_timezone_change(
        self, user, used_timezone: StaticTzInfo
    ):
        user_timezone = await store.get_user_timezone(user_id=user.id)
        if used_timezone and str(user_timezone) != str(used_timezone):
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

    async def _prompt_for_video_service(
        self,
        inter: GuildCommandInteraction,
        *,
        user: disnake.User | disnake.Member,
        guild: disnake.Guild,
    ) -> dict[str, Any]:
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
                    location="Zoom will be posted when event starts"
                ),
                channel_id=None,
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
                channel_id=None,
            )
        return video_service_kwargs


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Schedule(bot))
