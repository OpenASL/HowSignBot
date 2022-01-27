import logging
from typing import Optional

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands
from disnake.ext.commands import Bot, Cog, Context, command, is_owner, slash_command

from bot import __version__, settings
from bot.utils import truncate

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX


async def post_feedback(bot: commands.Bot, text: str, guild: Optional[str]):
    embed = disnake.Embed(title="Feedback received", description=text)
    if guild:
        embed.add_field(name="Guild", value=guild)
    embed.add_field(name="Version", value=__version__)
    assert bot.owner_id is not None
    owner = bot.get_user(bot.owner_id)
    assert owner is not None
    await owner.send(embed=embed)


class Meta(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @slash_command(name="feedback")
    async def feedback_command(self, inter: ApplicationCommandInteraction, text: str):
        """Anonymously share an idea or report a bug"""
        guild = inter.guild.name if inter.guild else None
        await post_feedback(self.bot, text, guild)
        await inter.send("🙌 Your feedback has been received! Thank you for your help.")

    @slash_command(name="invite")
    async def invite_command(self, inter: ApplicationCommandInteraction):
        """Invite HowSignBot to another Discord server"""
        url = disnake.utils.oauth_url(
            self.bot.user.id,
            permissions=disnake.Permissions(permissions=59456),
        )
        await inter.send(f"Add HowSignBot to another server here:\n<{url}>")

    @command(name="stats", hidden=True, help="BOT OWNER ONLY: Get bot stats")
    @is_owner()
    async def stats_command(self, ctx: Context):
        embed = disnake.Embed(title="HowSignBot Stats", color=disnake.Color.blue())
        n_guilds = len(self.bot.guilds)
        avg_members = round(
            sum(guild.member_count for guild in self.bot.guilds) / n_guilds
        )
        max_to_display = 40
        servers_display = "\n".join(
            f"{truncate(guild.name, 20)} `{guild.member_count}`"
            for guild in sorted(
                self.bot.guilds, key=lambda g: g.member_count, reverse=True
            )[:max_to_display]
        )
        remaining = max(n_guilds - max_to_display, 0)
        if remaining:
            servers_display += f"\n+{remaining} more"
        embed.add_field(
            name=f"Servers ({n_guilds}, avg {avg_members} users/server)",
            value=servers_display,
        )
        await ctx.send(embed=embed)

    @command(name="edit", hidden=True, help="BOT OWNER ONLY: Edit a bot message")
    @is_owner()
    async def edit_command(self, ctx: Context, message: disnake.Message):
        if message.author != self.bot.user:
            await ctx.send("⚠️ I didn't send that message.")
            return
        response = await ctx.reply(
            content=f"Reply to this message with the new message content for {message.jump_url}"
        )

        def check(m: disnake.Message):
            return (
                m.author == ctx.author
                and bool(m.reference)
                and m.reference.message_id == response.id
            )

        reply_message = await self.bot.wait_for("message", check=check)
        await message.edit(content=reply_message.content)
        await reply_message.reply(f"✅ Edited {message.jump_url}")


def setup(bot: Bot) -> None:
    bot.add_cog(Meta(bot))
