from __future__ import annotations

import datetime as dt
import logging
import math
import random
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

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

ASSETS_PATH = Path(__file__).parent / "assets"


async def make_user_star_count_embed(
    user: disnake.Member | disnake.User, *, description: str | None = None
) -> Embed:
    embed = Embed(
        description=description or "",
        color=disnake.Color.yellow(),
    )
    user_stars = await store.get_user_stars(user.id)
    embed.add_field(name=f"{STAR_EMOJI} count", value=str(user_stars))
    embed.set_author(
        name=display_name(user),
        icon_url=user.avatar.url if user.avatar else None,
    )
    return embed


REWARD_GIFS = sorted(ASSETS_PATH.glob("*.gif"))


def get_next_milestone(star_count: int, reward_milestones: list[int]) -> int:
    """Get the next milestone number of stars, given a current star_count."""
    next_milestone = next(
        (milestone for milestone in reward_milestones if milestone > star_count),
        None,
    )
    # After the last milestone in reward_milestones, return the next highest multiple of 5
    return next_milestone or int(math.ceil((star_count + 1) / 5.0)) * 5


HIGHLIGHT_PREFIXES = (
    f"{STAR_EMOJI} Great work here - ",
    f"{STAR_EMOJI} 10/10 - ",
    f"{STAR_EMOJI} CHAMP - ",
)


async def make_reward_send_kwargs(
    milestone: int,
    *,
    user_id: int,
    user_stars: int,
    last_reward_at: dt.datetime | None,
    reward_milestones: list[int],
) -> dict[str, Any]:
    if milestone in reward_milestones:
        index = reward_milestones.index(milestone)
        image_path = REWARD_GIFS[index % len(REWARD_GIFS)]
    else:
        image_path = random.choice(REWARD_GIFS)
    filename = "reward.gif"
    file_ = disnake.File(image_path, filename=filename)
    embed = disnake.Embed(
        title=f"🙌 You've earned {user_stars} {STAR_EMOJI}s!",
        description="Keep up the good work 👍",
        color=disnake.Color.yellow(),
    )
    embed.set_image(url=f"attachment://{filename}")
    star_logs = await store.list_user_star_highlight_logs(
        user_id=user_id, limit=3, after=last_reward_at
    )
    seen_logs = set()
    highlight_display = ""
    for i, log in enumerate(star_logs):
        if log["message_id"] not in seen_logs:
            highlight_display += f"{HIGHLIGHT_PREFIXES[i]}[Message]({log['jump_url']})\n"
            seen_logs.add(log["message_id"])
    if highlight_display:
        embed.add_field(
            name="Highlights",
            value=highlight_display,
        )
    next_milestone = get_next_milestone(user_stars, reward_milestones=reward_milestones)
    gap = next_milestone - user_stars
    noun = f"{STAR_EMOJI}s" if gap > 1 else STAR_EMOJI
    embed.add_field(name="Progress", value=f"Only {gap} {noun} until next milestone")
    return {"embed": embed, "file": file_}


async def maybe_reward_user(user: disnake.Member | disnake.User):
    guild_settings = await store.get_guild_settings(settings.SIGN_CAFE_GUILD_ID)
    if not guild_settings:
        return
    reward_milestones = guild_settings["reward_milestones"]
    if not reward_milestones:
        return
    last_reward_at, last_reward_star_count = None, 0
    last_reward = await store.get_latest_star_reward(user_id=user.id)
    if last_reward:
        last_reward_at = last_reward["created_at"]
        last_reward_star_count = last_reward["star_count"]

    next_milestone = get_next_milestone(
        last_reward_star_count, reward_milestones=reward_milestones
    )
    user_stars = await store.get_user_stars(user.id)
    if next_milestone and user_stars >= next_milestone:
        send_kwargs = await make_reward_send_kwargs(
            milestone=next_milestone,
            user_id=user.id,
            user_stars=user_stars,
            last_reward_at=last_reward_at,
            reward_milestones=reward_milestones,
        )
        with suppress(disnake.errors.Forbidden):  # user may not allow DMs from bot
            await user.send(**send_kwargs)
            await store.store_star_reward(user_id=user.id, star_count=user_stars)


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

    @stars_command.sub_command(name="milestones")
    @commands.has_permissions(kick_members=True)  # Staff
    async def stars_milestones(
        self,
        inter: GuildCommandInteraction,
    ):
        """(Authorized users only) Show the star reward milestones"""
        assert inter.guild_id is not None
        guild_settings = await store.get_guild_settings(guild_id=inter.guild_id)
        assert guild_settings is not None
        milestone_display = ",".join(str(m) for m in guild_settings["reward_milestones"])
        await inter.send(
            f"Current {STAR_EMOJI} milestones: {milestone_display}\nUse `/stars setmilestones` to update the milestones."
        )

    @stars_command.sub_command(name="setmilestones")
    @commands.has_permissions(kick_members=True)  # Staff
    async def stars_set_milestones(
        self,
        inter: GuildCommandInteraction,
        milestones: str,
    ):
        """(Authorized users only) Set the star reward milestones

        Parameters
        ----------
        milestones: Comma-separated list of integer values (example: 3,5,8,10,15)
        """
        try:
            milestone_list = [int(m) for m in milestones.split(",")]
            if any(m < 1 for m in milestone_list):
                raise ValueError
        except ValueError:
            await inter.send(
                "⚠️ Invalid value. Pass a comma-separated list of positive integers (example: `3,5,8,10,15`)."
            )
            return
        assert inter.guild_id is not None
        await store.update_reward_milestones(
            guild_id=inter.guild_id, reward_milestones=milestone_list
        )
        milestone_display = ",".join(str(m) for m in milestone_list)
        await inter.send(f"✅ Updated star reward milestones to: {milestone_display}")

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
                from_user_id=inter.user.id,
                to_user_id=user.id,
                n_stars=n,
                message_id=None,
                jump_url=None,
            )
        noun = f"{STAR_EMOJI}s" if n > 1 else f"a {STAR_EMOJI}"
        embed = await make_user_star_count_embed(
            description=f"{user.mention} received {noun} from {inter.user.mention}",
            user=user,
        )
        await inter.send(embed=embed)
        await maybe_reward_user(user)

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
                jump_url=None,
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
        self,
        inter: GuildCommandInteraction,
        user: disnake.User,
        stars: int = Param(ge=0),
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
        await maybe_reward_user(user)

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
                jump_url=message.jump_url,
            )
        channel = cast(
            disnake.TextChannel, self.bot.get_channel(settings.SIGN_CAFE_BOT_CHANNEL_ID)
        )
        embed = await make_user_star_count_embed(
            user=to_user,
            description=f"{to_user.mention} received a {STAR_EMOJI} from {from_user.mention} by a reaction\n[Source message]({message.jump_url})",
        )
        await channel.send(embed=embed)
        await maybe_reward_user(to_user)

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
                jump_url=message.jump_url,
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
