import logging
import random
from contextlib import suppress
from typing import Optional, Union, Sequence

import discord
from discord.ext.commands import Context, Bot, Cog, command

import cuteid
import catchphrase
from bot import settings
from bot.utils import did_you_mean
from bot.utils.reactions import should_handle_reaction, get_reaction_message

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
        logger.info("starting codenames game")
        message = await ctx.send(base_message)

        with suppress(Exception):
            await message.add_reaction("👍")
            await message.add_reaction("🔀")

    @Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        await self.handle_reaction(payload)

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self.handle_reaction(payload)

    async def handle_reaction(self, payload: discord.RawReactionActionEvent) -> None:
        if not should_handle_reaction(self.bot, payload, {"👍", "🔀"}):
            return
        message = await get_reaction_message(self.bot, payload)
        if not message:
            return
        # Was the message sent by the bot?
        if message.author.id != self.bot.user.id:
            return

        reaction = next((r for r in message.reactions if str(r.emoji) == "👍"), None)
        if not reaction:
            return
        players = [
            player
            for player in await reaction.users().flatten()
            if player.id != self.bot.user.id
        ]
        if str(reaction.emoji) == "🔀":
            random.shuffle(players)

        red, blue = make_teams(players)
        team_embed = discord.Embed(
            title="Teams",
            description=f"🔴 Red: {format_team(red)}\n🔵 Blue: {format_team(blue)}",
        )
        await message.edit(embed=team_embed)


def setup(bot: Bot) -> None:
    bot.add_cog(Games(bot))
