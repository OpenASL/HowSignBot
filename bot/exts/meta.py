import logging
from typing import Optional

import discord
from discord.ext import commands
from discord.ext.commands import Bot
from discord.ext.commands import Cog
from discord.ext.commands import command
from discord.ext.commands import Context
from discord.ext.commands import is_owner

from bot import __version__
from bot import settings
from bot.bot import set_default_presence
from bot.utils.datetimes import utcnow
from bot.utils.gsheets import get_gsheet_client

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX


def post_feedback(feedback: str, guild: Optional[str]):
    client = get_gsheet_client()
    # Assumes rows are in the format (date, feedback, guild, version)
    sheet = client.open_by_key(settings.FEEDBACK_SHEET_KEY)
    now = utcnow()
    worksheet = sheet.get_worksheet(0)
    row = (now.isoformat(), feedback, guild or "", __version__)
    logger.info(f"submitting feedback: {row}")
    return worksheet.append_row(row)


def ActivityTypeConverter(argument) -> discord.ActivityType:
    if argument not in discord.ActivityType._enum_member_names_:
        raise commands.CommandError(f'⚠️"{argument}" is not a valid activity type.')
    return getattr(discord.ActivityType, argument)


class Meta(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @command(name="invite", help="Invite HowSignBot to another Discord server")
    async def invite_command(self, ctx: Context):
        url = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=discord.Permissions(permissions=59456),
        )
        await ctx.send(f"Add HowSignBot to another server here:\n<{url}>")

    @command(name="feedback", help="Anonymously share an idea or report a bug")
    async def feedback_command(self, ctx: Context, *, feedback):
        await ctx.channel.trigger_typing()
        author = ctx.author
        guild = author.guild.name if hasattr(author, "guild") else None
        post_feedback(feedback, guild)
        await ctx.send("🙌 Your feedback has been received! Thank you for your help.")

    @feedback_command.error
    async def feedback_error(self, ctx, error):
        if isinstance(error, commands.errors.MissingRequiredArgument):
            await ctx.send(
                f"I ♥️ feedback! Enter a your feedback after `{COMMAND_PREFIX}feedback`"
            )

    @command(name="presence", hidden=True, help="BOT OWNER ONLY: Change bot presense")
    @is_owner()
    async def presence_command(self, ctx: Context, activity_type: Optional[ActivityTypeConverter] = None, name: str = ""):  # type: ignore[valid-type]
        if not activity_type:
            await set_default_presence()
            await ctx.send("Presence reset.")
            return
        activity = discord.Activity(
            name=name.format(p=COMMAND_PREFIX),
            type=activity_type,
        )
        logger.info(f"changing presence to {activity}")
        await self.bot.change_presence(activity=activity)
        await ctx.send(f"Changed presence to: `{activity}`")

    @command(name="stats", hidden=True, help="BOT OWNER ONLY: Get bot stats")
    @is_owner()
    async def stats_command(self, ctx: Context):
        embed = discord.Embed(title="HowSignBot Stats", color=discord.Color.blue())
        n_guilds = len(self.bot.guilds)
        avg_members = round(
            sum(guild.member_count for guild in self.bot.guilds) / n_guilds
        )
        max_to_display = 50
        servers_display = "\n".join(
            f"{guild.name} `{guild.member_count}`" for guild in self.bot.guilds
        )
        remaining = max(n_guilds - max_to_display, 0)
        if remaining:
            servers_display += f"\n+{remaining} more"
        embed.add_field(
            name=f"Servers ({n_guilds}, avg {avg_members} users/server)",
            value=servers_display,
        )
        await ctx.send(embed=embed)


def setup(bot: Bot) -> None:
    bot.add_cog(Meta(bot))
