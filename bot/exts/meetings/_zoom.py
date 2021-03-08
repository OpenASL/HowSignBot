import asyncio
import logging
import random
from contextlib import suppress
from typing import Sequence, List, Optional, Callable, Awaitable, Tuple

import discord
from aiohttp import client
from databases.backends.postgres import Record
from discord.ext.commands import Context, errors, Bot
from nameparser import HumanName

import holiday_emojis
import meetings
from bot import settings
from bot.utils.datetimes import utcnow, PACIFIC
from bot.database import store

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX

REPOST_EMOJI = "↩️"
REPOST_EMOJI_DELAY = 30
ZOOM_CLOSED_MESSAGE = "✨ _Zoom meeting ended_"

FACES = (
    "😀",
    "😃",
    "😄",
    "😁",
    "😆",
    "😅",
    "🤣",
    "😂",
    "🙂",
    "🙃",
    "😉",
    "😇",
    "🥰",
    "😍",
    "😊",
    "🤩",
    "☺️",
    "🥲",
    "😋",
    "😛",
    "😜",
    "🤪",
    "😝",
    "🤑",
    "🤗",
    "🤭",
    "🤫",
    "🤔",
    "🤐",
    "🤨",
    "🙄",
    "🤤",
    "😐",
    "😶",
    "😑",
    "😏",
    "😬",
    "😌",
    "😴",
    "😷",
    "🥴",
    "😵",
    "🤯",
    "🥱",
    "🤠",
    "🥳",
    "🥸",
    "😎",
    "🤓",
    "😺",
    "😸",
    "😹",
    "😼",
    "🙀",
)


def display_participant_names(
    participants: Sequence[Record], meeting: Record, max_to_display: int = 15
) -> str:
    names: List[str] = []
    for participant in participants:
        if participant["email"] in settings.ZOOM_EMAILS:
            # Display authorized zoom users as mentions
            discord_id = settings.ZOOM_EMAILS[participant["email"]]
            display_name = f"<@{discord_id}>"
        else:
            # Only display first name to save real estate, fall back to full name
            display_name = HumanName(participant["name"]).first or participant["name"]
        if participant["zoom_id"] and participant["zoom_id"] == meeting["host_id"]:
            # Display host first and in bold
            names.insert(0, f"**{display_name}**")
        else:
            names.append(display_name)
    ret = "\n".join(
        f"{get_participant_emoji()} {name}" for name in names[:max_to_display]
    )
    remaining = max(len(names) - max_to_display, 0)
    if remaining:
        ret += f"\n+{remaining} more"
    return ret


def get_participant_emoji() -> str:
    if settings.PARTICIPANT_EMOJI:
        return random.choice(settings.PARTICIPANT_EMOJI)
    today_pacific = utcnow().astimezone(PACIFIC).date()
    holiday_name = holiday_emojis.get_holiday_name(today_pacific)
    if holiday_name == "Halloween":
        return "👻"
    elif holiday_name == "Thanksgiving":
        return "🦃"
    elif holiday_name in {"Christmas Eve", "Christmas Day"}:
        return "🎄"
    elif today_pacific.month == 12:
        return "⛄️"
    return random.choice(FACES)


async def make_zoom_embed(
    meeting_id: int,
    *,
    include_instructions: bool = True,
) -> discord.Embed:
    meeting = await store.get_zoom_meeting(meeting_id)
    title = f"<{meeting['join_url']}>"
    description = f"**Meeting ID:**: {meeting_id}\n**Passcode**: {meeting['passcode']}"
    if meeting["topic"]:
        description = f"{description}\n**Topic**: {meeting['topic']}"
    if include_instructions:
        description += "\n🚀 This meeting is happening now. Go practice!\n**If you're in the waiting room for more than 10 seconds, @-mention the host below with your Zoom display name.**"
    embed = discord.Embed(
        color=discord.Color.blue(),
    )
    embed.add_field(name=title, value=description)
    embed.set_author(
        name="Join Meeting",
        url=meeting["join_url"],
        icon_url="https://user-images.githubusercontent.com/2379650/109329673-df945f80-7828-11eb-9e35-1b60b6e7bb93.png",
    )
    if include_instructions:
        embed.set_footer(text="This message will be cleared when the meeting ends.")

    participants = tuple(await store.get_zoom_participants(meeting_id))
    if participants:
        participant_names = display_participant_names(
            participants=participants, meeting=meeting
        )
        embed.add_field(name="👥 Participants", value=participant_names, inline=True)

    return embed


def is_allowed_zoom_access(ctx: Context):
    if ctx.author.id not in settings.ZOOM_USERS:
        raise errors.CheckFailure(
            f"⚠️ `{COMMAND_PREFIX}{ctx.command}` can only be used by authorized users under the bot owner's Zoom account."
        )
    return True


async def maybe_create_zoom_meeting(zoom_user: str, meeting_id: int, set_up: bool):
    meeting_exists = await store.zoom_meeting_exists(meeting_id=meeting_id)
    if not meeting_exists:
        try:
            meeting = await meetings.get_zoom(
                token=settings.ZOOM_JWT, meeting_id=meeting_id
            )
        except client.ClientResponseError as error:
            logger.exception(f"error when fetching zoom meeting {meeting_id}")
            raise errors.CheckFailure(
                f"⚠️ Could not find Zoom meeting with ID {meeting_id}. Double check the ID or use `{COMMAND_PREFIX}zoom` to create a new meeting."
            ) from error
        else:
            await store.create_zoom_meeting(
                zoom_user=zoom_user,
                meeting_id=meeting.id,
                join_url=meeting.join_url,
                passcode=meeting.passcode,
                topic=meeting.topic,
                set_up=set_up,
            )


class ZoomCreateError(errors.CommandError):
    pass


async def add_repost_after_delay_impl(message: discord.Message, delay: int):
    await asyncio.sleep(delay)
    with suppress(Exception):
        await message.add_reaction(REPOST_EMOJI)


def add_repost_after_delay(
    bot: Bot, message: discord.Message, delay: int = REPOST_EMOJI_DELAY
):
    bot.loop.create_task(add_repost_after_delay_impl(message, delay))


async def zoom_impl(
    ctx: Context,
    *,
    meeting_id: Optional[int],
    send_channel_message: Callable[[int], Awaitable],
    set_up: bool,
) -> Tuple[int, discord.Message]:
    zoom_user = settings.ZOOM_USERS[ctx.author.id]
    logger.info(f"creating zoom meeting for zoom user: {zoom_user}")
    message = None
    if meeting_id:
        async with store.transaction():
            await maybe_create_zoom_meeting(zoom_user, meeting_id, set_up=set_up)
            message = await send_channel_message(meeting_id)
            if set_up:
                add_repost_after_delay(ctx.bot, message)
            logger.info(
                f"creating zoom meeting message for message {message.id} in channel {ctx.channel.id}"
            )
            await store.create_zoom_message(
                meeting_id=meeting_id, message_id=message.id, channel_id=ctx.channel.id
            )
        return meeting_id, message
    else:
        try:
            meeting = await meetings.create_zoom(
                token=settings.ZOOM_JWT,
                user_id=zoom_user,
                topic="",
                settings={
                    "host_video": False,
                    "participant_video": False,
                    "mute_upon_entry": True,
                    "waiting_room": True,
                },
            )
        except Exception as error:
            raise ZoomCreateError(
                "🚨 _Could not create Zoom meeting. That's embarrassing._"
            ) from error
        else:
            logger.info(f"creating meeting {meeting_id}")
            async with store.transaction():
                await store.create_zoom_meeting(
                    zoom_user=zoom_user,
                    meeting_id=meeting.id,
                    join_url=meeting.join_url,
                    passcode=meeting.passcode,
                    topic=meeting.topic,
                    set_up=set_up,
                )
                message = await send_channel_message(meeting.id)
                if set_up:
                    add_repost_after_delay(ctx.bot, message)
                logger.info(
                    f"creating zoom meeting message for message {message.id} in channel {ctx.channel.id}"
                )
                await store.create_zoom_message(
                    meeting_id=meeting.id,
                    message_id=message.id,
                    channel_id=ctx.channel.id,
                )
            return meeting.id, message
