import logging
import re
from contextlib import suppress
from typing import Awaitable, Callable, Iterable, Mapping, Optional, Union

import disnake
from disnake.ext.commands import Bot

logger = logging.getLogger(__name__)

STOP_SIGN = "🛑"


async def maybe_clear_reaction(message: disnake.Message, emoji: str, *, log: bool = True):
    try:
        await message.clear_reaction(emoji)
    except Exception:
        if log:
            logger.exception("could not remove reaction")


async def maybe_add_reaction(message: disnake.Message, emoji: str, *, log: bool = False):
    try:
        await message.add_reaction(emoji)
    except Exception:
        if log:
            logger.exception("could not add reaction")


async def add_stop_sign(message: disnake.Message):
    await maybe_add_reaction(message, STOP_SIGN)


async def get_reaction_message(
    bot: Bot,
    payload: disnake.RawReactionActionEvent,
) -> Optional[disnake.Message]:
    with suppress(disnake.NotFound):
        channel = bot.get_channel(payload.channel_id)
        if not channel:
            return None
        message: disnake.Message = await channel.fetch_message(payload.message_id)
    return message


def reactor_is_human(bot: Bot, payload: disnake.RawReactionActionEvent) -> bool:
    with suppress(disnake.NotFound):
        member = bot.get_user(payload.user_id)
    return not bool(getattr(member, "bot", None))


def should_handle_reaction(
    bot: Bot, payload: disnake.RawReactionActionEvent, emojis: Iterable[str]
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
    payload: disnake.RawReactionActionEvent,
    *,
    close_messages: Mapping[str, Union[str, Callable[[disnake.Message], Awaitable]]],
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
                    if callable(close_message):
                        close_message = await close_message(message)
                    logger.info(f"cleaning up room with message: {close_message}")
                    await message.edit(content=close_message, embed=None)
                    return
                for field in embed.fields:
                    if field.name and re.search(pattern, field.name):
                        if callable(close_message):
                            close_message = await close_message(message)
                        logger.info(f"cleaning up room with message: {close_message}")
                        await message.edit(content=close_message, embed=None)
                        return
        if re.search(pattern, message.content):
            if callable(close_message):
                close_message = await close_message(message)
            logger.info(f"cleaning up room with message: {close_message}")
            await message.edit(content=close_message, embed=None)
            return
