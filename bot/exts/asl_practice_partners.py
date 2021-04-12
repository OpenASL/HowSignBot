import asyncio
import logging
from typing import List

from discord.channel import TextChannel
from discord.ext import commands
from discord.ext.commands import Bot
from discord.ext.commands import Cog
from discord.ext.commands import Context
from discord.ext.commands import group
from discord.ext.commands import is_owner

from bot import settings
from bot.utils.gsheets import get_gsheet_client

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX


def get_gsheet():
    client = get_gsheet_client()
    return client.open_by_key(settings.ASLPP_SHEET_KEY)


def get_sheet_content(worksheet_name: str) -> List[str]:
    sheet = get_gsheet()
    worksheet = sheet.worksheet(worksheet_name)
    # Get all content from first column
    return worksheet.col_values(1)


class AslPracticePartners(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @group(name="aslpp", hidden=True)
    @is_owner()
    async def aslpp_group(self, ctx: Context):
        pass

    @aslpp_group.command(name="faq", hidden=True)
    @is_owner()
    async def faq_command(self, ctx: Context, channel: TextChannel):
        await ctx.channel.trigger_typing()
        for content in get_sheet_content("faq"):
            await channel.send(content)
            # Sleep to ensure messages are always displayed in the correct order
            await asyncio.sleep(1)
        await ctx.reply("🙌 FAQ posted")

    @aslpp_group.command(name="rules", hidden=True)
    @is_owner()
    async def rules_command(self, ctx: Context, channel: TextChannel):
        await ctx.channel.trigger_typing()
        for content in get_sheet_content("rules"):
            await channel.send(content)
            # Sleep to ensure messages are always displayed in the correct order
            await asyncio.sleep(1)
        await ctx.reply("🙌 Rules posted")


def setup(bot: Bot) -> None:
    bot.add_cog(AslPracticePartners(bot))
