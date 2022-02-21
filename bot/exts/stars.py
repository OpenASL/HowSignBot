from __future__ import annotations

import logging
from typing import cast

import disnake
from disnake import Embed, GuildCommandInteraction
from disnake.ext import commands
from disnake.ext.commands import Bot, Cog, Context, slash_command

from bot import settings
from bot.database import store
from bot.utils.discord import display_name
from bot.utils.reactions import get_reaction_message, should_handle_reaction

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX
STAR_EMOJI = "⭐"


class Stars(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_check(self, ctx: Context):
        if not bool(ctx.guild) or ctx.guild.id != settings.SIGN_CAFE_GUILD_ID:
            raise commands.errors.CheckFailure(
                f"⚠️ `{COMMAND_PREFIX}{ctx.invoked_with}` must be run within the Sign Cafe server (not a DM)."
            )
        return True

    @slash_command(name="stars", guild_ids=(settings.SIGN_CAFE_GUILD_ID,))
    async def stars_command(self, inter: GuildCommandInteraction):
        pass

    @stars_command.sub_command(name="set")
    @commands.has_permissions(kick_members=True)  # Staff
    async def stars_set(
        self, inter: GuildCommandInteraction, user: disnake.User, stars: int
    ):
        """(Authorized users only) Set a user's star count

        Parameters
        ----------
        user: The user to change
        stars: The star count to set
        """
        assert inter.user is not None
        async with store.transaction():
            await store.set_user_stars(
                from_user_id=inter.user.id,
                to_user_id=user.id,
                star_count=stars,
            )
        embed = Embed(
            description=f"Set star count for {user.mention}", color=disnake.Color.yellow()
        )
        user_stars = await store.get_user_stars(user.id)
        embed.add_field(name=f"{STAR_EMOJI} count", value=str(user_stars))
        embed.set_author(
            name=display_name(user),
            icon_url=user.avatar.url if user.avatar else Embed.Empty,
        )
        await inter.response.send_message(embed=embed)

    @stars_command.sub_command(name="board")
    async def stars_board(self, inter: GuildCommandInteraction):
        """Show the star leaderboard"""
        records = await store.list_user_stars(limit=10)
        embed = Embed(
            title=f"{STAR_EMOJI} Leaderboard",
            description="\n".join(
                [
                    f"{i+1}. <@{record['user_id']}> | {record['star_count']} {STAR_EMOJI}"
                    for i, record in enumerate(records)
                ]
            ),
            color=disnake.Color.yellow(),
        )
        await inter.response.send_message(embed=embed)

    async def maybe_get_star_reaction_message_and_user(
        self,
        payload: disnake.RawReactionActionEvent,
    ) -> tuple[disnake.Message | None, disnake.Member | None]:
        if not settings.SIGN_CAFE_ENABLE_STARS:
            return None, None
        if not should_handle_reaction(self.bot, payload, {STAR_EMOJI}):
            return None, None
        message = await get_reaction_message(self.bot, payload)
        if not message:
            return None, None
        if not message.guild:
            return None, None
        if not message.guild.id == settings.SIGN_CAFE_GUILD_ID:
            return None, None
        if bool(getattr(message.author, "bot", None)):  # User is a bot
            return None, None
        channel = cast(disnake.TextChannel, message.channel)
        if not channel.guild:
            return None, None
        from_user = await channel.guild.get_or_fetch_member(payload.user_id)
        if not from_user:
            return None, None
        permissions = channel.permissions_for(from_user)
        is_staff = getattr(permissions, "kick_members", False) is True
        if not is_staff:
            return None, None
        return message, from_user

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: disnake.RawReactionActionEvent) -> None:
        message, from_user = await self.maybe_get_star_reaction_message_and_user(payload)
        if message is None or from_user is None:
            return

        to_user = message.author

        async with store.transaction():
            await store.give_star(
                from_user_id=from_user.id,
                to_user_id=to_user.id,
                message_id=message.id,
            )
        channel = cast(
            disnake.TextChannel, self.bot.get_channel(settings.SIGN_CAFE_BOT_CHANNEL_ID)
        )
        embed = Embed(
            description=f"{to_user.mention} received a {STAR_EMOJI} from {from_user.mention}\n[Source message]({message.jump_url})",
            color=disnake.Color.yellow(),
        )
        user_stars = await store.get_user_stars(to_user.id)
        embed.add_field(name=f"{STAR_EMOJI} count", value=str(user_stars))
        embed.set_author(
            name=display_name(to_user),
            icon_url=to_user.avatar.url if to_user.avatar else Embed.Empty,
        )
        await channel.send(embed=embed)

    @Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: disnake.RawReactionActionEvent
    ) -> None:
        message, from_user = await self.maybe_get_star_reaction_message_and_user(payload)
        if message is None or from_user is None:
            return

        to_user = message.author

        async with store.transaction():
            await store.remove_star(
                from_user_id=from_user.id,
                to_user_id=to_user.id,
                message_id=message.id,
            )
        channel = cast(
            disnake.TextChannel, self.bot.get_channel(settings.SIGN_CAFE_BOT_CHANNEL_ID)
        )
        embed = Embed(
            description=f"{to_user.mention} removed a {STAR_EMOJI} from {from_user.mention}\n[Source message]({message.jump_url})",
            color=disnake.Color.yellow(),
        )
        user_stars = await store.get_user_stars(to_user.id)
        embed.add_field(name=f"{STAR_EMOJI} count", value=str(user_stars))
        embed.set_author(
            name=display_name(to_user),
            icon_url=to_user.avatar.url if to_user.avatar else Embed.Empty,
        )
        await channel.send(embed=embed)


def setup(bot: Bot) -> None:
    bot.add_cog(Stars(bot))
