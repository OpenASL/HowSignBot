from __future__ import annotations

import logging
from typing import cast

import disnake
from disnake import Embed, GuildCommandInteraction
from disnake.ext import commands
from disnake.ext.commands import Bot, Cog, Context, Param, slash_command

from bot import settings
from bot.database import store
from bot.utils.discord import display_name
from bot.utils.reactions import get_reaction_message, should_handle_reaction

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX
STAR_EMOJI = "⭐"


async def make_user_star_count_embed(
    user: disnake.Member | disnake.User, *, description: str | None = None
) -> Embed:
    embed = Embed(
        description=description or Embed.Empty,
        color=disnake.Color.yellow(),
    )
    user_stars = await store.get_user_stars(user.id)
    embed.add_field(name=f"{STAR_EMOJI} count", value=str(user_stars))
    embed.set_author(
        name=display_name(user),
        icon_url=user.avatar.url if user.avatar else Embed.Empty,
    )
    return embed


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

    @stars_command.sub_command(name="give")
    @commands.has_permissions(kick_members=True)  # Staff
    async def stars_give(
        self,
        inter: GuildCommandInteraction,
        user: disnake.User,
        n: int = Param(ge=0, default=1),
    ):
        """(Authorized users only) Give a star to a user

        Parameters
        ----------
        user: The user to give a star to
        n: The number of stars to give
        """
        assert inter.user is not None
        async with store.transaction():
            await store.give_stars(
                from_user_id=inter.user.id, to_user_id=user.id, n_stars=n, message_id=None
            )
        noun = f"{STAR_EMOJI}s" if n > 1 else f"a {STAR_EMOJI}"
        embed = await make_user_star_count_embed(
            description=f"{user.mention} received {noun} from {inter.user.mention}",
            user=user,
        )
        await inter.send(embed=embed)

    @stars_command.sub_command(name="remove")
    @commands.has_permissions(kick_members=True)  # Staff
    async def stars_remove(
        self,
        inter: GuildCommandInteraction,
        user: disnake.User,
        n: int = Param(ge=0, default=1),
    ):
        """(Authorized users only) Remove a star from a user

        Parameters
        ----------
        user: The user to remove a star from
        n: The number of stars to remove
        """
        assert inter.user is not None
        async with store.transaction():
            await store.remove_stars(
                from_user_id=inter.user.id,
                to_user_id=user.id,
                n_stars=n,
                message_id=None,
            )
        assert inter.user is not None
        noun = f"{STAR_EMOJI}s" if n > 1 else f"a {STAR_EMOJI}"
        embed = await make_user_star_count_embed(
            description=f"{user.mention} had {noun} removed by {inter.user.mention}",
            user=user,
        )
        await inter.send(embed=embed)

    @stars_command.sub_command(name="set")
    @commands.has_permissions(kick_members=True)  # Staff
    async def stars_set(
        self, inter: GuildCommandInteraction, user: disnake.User, stars: int = Param(ge=0)
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
        embed = await make_user_star_count_embed(
            user=user, description=f"Set star count for {user.mention}"
        )
        await inter.response.send_message(embed=embed)

    @stars_command.sub_command(name="board")
    async def stars_board(self, inter: GuildCommandInteraction):
        """Show the star leaderboard"""
        records = await store.list_user_stars(limit=100)
        description = ""
        # TODO: use a paginated embed
        # https://discord.com/developers/docs/resources/channel#embed-limits
        max_description_length = 4096
        for i, record in enumerate(records):
            member = await inter.guild.get_or_fetch_member(record["user_id"])
            if not member:
                continue
            line = f"{i+1}. {member.display_name} | `{member.name}#{member.discriminator}` | {record['star_count']} {STAR_EMOJI}\n"
            if len(description) + len(line) < max_description_length:
                description += line
        embed = Embed(
            title=f"{STAR_EMOJI} Leaderboard",
            description=description,
            color=disnake.Color.yellow(),
        )
        await inter.response.send_message(embed=embed)

    @stars_command.sub_command(name="me")
    async def stars_me(self, inter: GuildCommandInteraction):
        """Show how many stars you have"""
        assert inter.user is not None
        embed = await make_user_star_count_embed(user=inter.user)
        await inter.send(embed=embed)

    @stars_command.sub_command(name="info")
    async def stars_info(self, inter: GuildCommandInteraction, user: disnake.User):
        """Show how many stars a user has"""
        embed = await make_user_star_count_embed(user=user)
        await inter.send(embed=embed)

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: disnake.RawReactionActionEvent) -> None:
        message, from_user = await self._maybe_get_star_reaction_message_and_user(payload)
        if message is None or from_user is None:
            return

        to_user = message.author

        async with store.transaction():
            await store.give_stars(
                from_user_id=from_user.id,
                to_user_id=to_user.id,
                n_stars=1,
                message_id=message.id,
            )
        channel = cast(
            disnake.TextChannel, self.bot.get_channel(settings.SIGN_CAFE_BOT_CHANNEL_ID)
        )
        embed = await make_user_star_count_embed(
            user=to_user,
            description=f"{to_user.mention} received a {STAR_EMOJI} from {from_user.mention} by a reaction\n[Source message]({message.jump_url})",
        )
        await channel.send(embed=embed)

    @Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: disnake.RawReactionActionEvent
    ) -> None:
        message, from_user = await self._maybe_get_star_reaction_message_and_user(payload)
        if message is None or from_user is None:
            return

        to_user = message.author

        async with store.transaction():
            await store.remove_stars(
                from_user_id=from_user.id,
                to_user_id=to_user.id,
                n_stars=1,
                message_id=message.id,
            )
        channel = cast(
            disnake.TextChannel, self.bot.get_channel(settings.SIGN_CAFE_BOT_CHANNEL_ID)
        )
        embed = await make_user_star_count_embed(
            user=to_user,
            description=f"{to_user.mention} had a {STAR_EMOJI} removed by {from_user.mention}\n[Source message]({message.jump_url})",
        )
        await channel.send(embed=embed)

    async def _maybe_get_star_reaction_message_and_user(
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
        if message.guild.id != settings.SIGN_CAFE_GUILD_ID:
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


def setup(bot: Bot) -> None:
    bot.add_cog(Stars(bot))
