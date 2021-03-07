import logging
import random
from contextlib import suppress
from typing import Iterable, Optional, Union, Sequence

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

    @Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        if not self.should_handle_reaction(payload, {"👍"}):
            return
        message = await self.get_reaction_message(payload)
        if not message:
            return

        if str(payload.emoji) == "👍":
            reaction = next((r for r in message.reactions if str(r.emoji) == "👍"), None)
            if not reaction:
                return
            players = [
                player
                for player in await reaction.users().flatten()
                if player.id != self.bot.user.id
            ]
            red, blue = make_teams(players)
            team_embed = discord.Embed(
                title="Teams",
                description=f"🔴 Red: {format_team(red)}\n🔵 Blue: {format_team(blue)}",
            )
            await message.edit(embed=team_embed)

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if not self.should_handle_reaction(payload, {"👍", "🔀"}):
            return

        message = await self.get_reaction_message(payload)
        if not message:
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

    def should_handle_reaction(
        self, payload: discord.RawReactionActionEvent, emojis: Iterable[str]
    ) -> bool:
        # Is this a control emoji?
        if str(payload.emoji) not in emojis:
            return False
        # Was the message sent in a channel (not a DM)?
        if not payload.channel_id:
            return False
        if not self.reactor_is_human(payload):
            return False
        return True

    async def get_reaction_message(
        self,
        payload: discord.RawReactionActionEvent,
    ) -> Optional[discord.Message]:
        with suppress(discord.NotFound):
            channel = self.bot.get_channel(payload.channel_id)
            if not channel:
                return None
            message: discord.Message = await channel.fetch_message(payload.message_id)
        return message

    def reactor_is_human(self, payload: discord.RawReactionActionEvent) -> bool:
        with suppress(discord.NotFound):
            member = self.bot.get_user(payload.user_id)
        return not bool(getattr(member, "bot", None))


def setup(bot: Bot) -> None:
    bot.add_cog(Games(bot))
