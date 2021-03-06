import asyncio
import logging
import random
from contextlib import suppress
from typing import Optional, List, Union, Sequence

import discord
from discord.ext.commands import Context, Bot, Cog, command

import cuteid
import catchphrase
from bot import settings
from bot.utils import did_you_mean

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX

NUM_CATCHPHRASE_WORDS = 8

CATEGORIES_FORMATTED = ", ".join(catchphrase.CATEGORIES)


def catchphrase_impl(category: Optional[str] = None):
    category = category.lower() if category else None
    if category == "categories":
        return {
            "content": f"{CATEGORIES_FORMATTED}\nEnter `{COMMAND_PREFIX}cp` or `{COMMAND_PREFIX}cp [category]` to generate a list of words/phrases."
        }

    if category and category not in catchphrase.CATEGORIES:
        logger.info(f"invalid category: {category}")
        suggestion = did_you_mean(category, catchphrase.CATEGORIES)
        if suggestion:
            return {
                "content": f'"{category}" is not a valid category. Did you mean "{suggestion}"?\nCategories: {CATEGORIES_FORMATTED}'
            }
        else:
            return {
                "content": f'"{category}" is not a valid category.\nCategories: {CATEGORIES_FORMATTED}'
            }
    words = "\n".join(
        f"||{catchphrase.catchphrase(category)}||" for _ in range(NUM_CATCHPHRASE_WORDS)
    )
    message = f"{words}\nEnter `{COMMAND_PREFIX}cp` or `{COMMAND_PREFIX}cp [category]` for more.\nCategories: {CATEGORIES_FORMATTED}"
    logger.info("sending catchphrase words/phrases")
    return {"content": message}


def make_teams(players):
    red, blue = [], []
    for player in reversed(players):
        if len(red) == len(blue):
            team = random.choice([red, blue])
        else:
            team = min(red, blue, key=len)
        team.append(player)
    return red, blue


def format_team(players: Sequence[Union[discord.User, discord.Member]]):
    names = [each.mention for each in players]
    return ", ".join(names)


class Games(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @command(
        name="catchphrase",
        aliases=("cp",),
        help="Generate a list of random words and phrases",
    )
    async def catchphrase_command(self, ctx: Context, category: Optional[str] = None):
        await ctx.send(**catchphrase_impl(category))

    @command(name="codenames", aliases=("cn",), help="Start a Codenames game")
    async def codenames_command(self, ctx: Context, name: Optional[str] = None):
        name = name or cuteid.cuteid()
        url = f"https://horsepaste.com/{name}"
        base_message = f"🕵️ **Codenames** 🕵️\n{url}\nClick 👍 to join a team. Click 🔀 to shuffle the teams."
        logger.info(f"starting codenames game at {url}")
        message = await ctx.send(base_message)

        with suppress(Exception):
            await message.add_reaction("👍")
            await message.add_reaction("🔀")

        def check(reaction, user):
            return reaction.message.id == message.id

        players: List[Union[discord.User, discord.Member]] = []
        while True:
            done, pending = await asyncio.wait(
                (
                    asyncio.create_task(self.bot.wait_for("reaction_add", check=check)),
                    asyncio.create_task(
                        self.bot.wait_for("reaction_remove", check=check)
                    ),
                ),
                return_when=asyncio.FIRST_COMPLETED,
            )
            reaction, _ = done.pop().result()
            for future in pending:
                future.cancel()
            if str(reaction.emoji) in ("👍", "🔀"):
                if str(reaction.emoji) == "🔀":
                    logger.info("shuffling players")
                    random.shuffle(players)
                else:
                    players = [
                        player
                        for player in await reaction.users().flatten()
                        if player.id != self.bot.user.id
                    ]
                red, blue = make_teams(players)
                logger.info(f"total players: {len(players)}")
                await message.edit(
                    content=f"{base_message}\n🔴 Red: {format_team(red)}\n🔵 Blue: {format_team(blue)}"
                )


def setup(bot: Bot) -> None:
    bot.add_cog(Games(bot))
