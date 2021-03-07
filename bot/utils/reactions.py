import logging
import re
from contextlib import suppress
from typing import Mapping, Optional, Iterable

import discord
from discord.ext.commands import Bot

logger = logging.getLogger(__name__)

STOP_SIGN = "🛑"


async def add_stop_sign(bot: Bot, message: discord.Message):
    with suppress(Exception):
        await message.add_reaction(STOP_SIGN)


async def get_reaction_message(
    bot: Bot,
    payload: discord.RawReactionActionEvent,
) -> Optional[discord.Message]:
    with suppress(discord.NotFound):
        channel = bot.get_channel(payload.channel_id)
        if not channel:
            return None
        message: discord.Message = await channel.fetch_message(payload.message_id)
    return message


def reactor_is_human(bot: Bot, payload: discord.RawReactionActionEvent) -> bool:
    with suppress(discord.NotFound):
        member = bot.get_user(payload.user_id)
    return not bool(getattr(member, "bot", None))


def should_handle_reaction(
    bot: Bot, payload: discord.RawReactionActionEvent, emojis: Iterable[str]
) -> bool:
    # Is this a control emoji?
    if str(payload.emoji) not in emojis:
        return False
    # Was the message sent in a channel (not a DM)?
    if not payload.channel_id:
        return False
    if not reactor_is_human(bot, payload):
        return False
    return True


async def handle_close_reaction(
    bot: Bot,
    payload: discord.RawReactionActionEvent,
    *,
    close_messages: Mapping[str, str],
    emoji: str = STOP_SIGN,
) -> None:
    if not should_handle_reaction(bot, payload, {emoji}):
        return
    message = await get_reaction_message(bot, payload)
    if not message:
        return
    # Was the message sent by the bot?
    if message.author.id != bot.user.id:
        return

    for pattern, close_message in close_messages.items():
        # Scan the message for the pattern and replace it with close_message if found
        if message.embeds:
            for embed in message.embeds:
                if embed.title and re.search(pattern, embed.title):
                    logger.info(f"cleaning up room with message: {close_message}")
                    await message.edit(content=close_message, embed=None)
                    return
                for field in embed.fields:
                    if field.name and re.search(pattern, field.name):
                        logger.info(f"cleaning up room with message: {close_message}")
                        await message.edit(content=close_message, embed=None)
                        return
        if re.search(pattern, message.content):
            logger.info(f"cleaning up room with message: {close_message}")
            await message.edit(content=close_message, embed=None)
            return
