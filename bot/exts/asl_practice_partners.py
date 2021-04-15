import asyncio
import logging
from typing import List

from discord import Color
from discord import Embed
from discord import Member
from discord import Message
from discord.channel import TextChannel
from discord.ext import commands
from discord.ext.commands import Bot
from discord.ext.commands import Cog
from discord.ext.commands import Context
from discord.ext.commands import group
from discord.ext.commands import is_owner

from bot import settings
from bot.database import store
from bot.utils.datetimes import utcnow
from bot.utils.gsheets import get_gsheet_client
from bot.utils.pagination import LinePaginator

logger = logging.getLogger(__name__)


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

    # TODO: Allow mods/admins to use these commands

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

    @aslpp_group.command(name="welcome", hidden=True)
    @is_owner()
    async def welcome_command(self, ctx: Context, channel: TextChannel):
        await ctx.channel.trigger_typing()
        for content in get_sheet_content("welcome"):
            await channel.send(content)
            # Sleep to ensure messages are always displayed in the correct order
            await asyncio.sleep(1)
        await ctx.reply("🙌 Welcome message posted")

    @aslpp_group.command(name="video", hidden=True)
    @is_owner()
    async def video_command(self, ctx: Context, channel: TextChannel):
        await ctx.channel.trigger_typing()
        for content in get_sheet_content("video-etiquette"):
            await channel.send(content)
            # Sleep to ensure messages are always displayed in the correct order
            await asyncio.sleep(1)
        await ctx.reply("🙌 Video etiquette message posted")

    @aslpp_group.command(name="syncdata", hidden=True)
    @is_owner()
    async def sync_data_command(self, ctx: Context):
        await ctx.channel.trigger_typing()
        channel = self.bot.get_channel(settings.ASLPP_INTRODUCTIONS_CHANNEL_ID)
        async for message in channel.history(limit=20):
            logger.info(f"storing intro record {message.id}")
            await store.add_aslpp_intro(
                message_id=message.id,
                user_id=message.author.id,
                posted_at=message.created_at,
            )

        role = ctx.guild.get_role(settings.ASLPP_ACKNOWLEDGED_RULES_ROLE_ID)
        for member in role.members:
            logger.info(f"storing member {member.id}")
            await store.add_aslpp_member(user_id=member.id, joined_at=member.joined_at)
        await ctx.reply("🙌 Synced data")

    @aslpp_group.command(name="nointros", hidden=True)
    @is_owner()
    async def no_intros_command(self, ctx: Context):
        await ctx.channel.trigger_typing()
        members_without_intro = await store.get_aslpp_members_without_intro()

        embed = Embed(
            title="These users have acknowledged the rules but haven't posted an intro:",
            color=Color.orange(),
        )
        lines = [
            f"<@!{member['user_id']}> - Member for {(utcnow() - member['joined_at']).days} days"
            for member in members_without_intro
        ]
        await LinePaginator.paginate(
            lines, ctx=ctx, embed=embed, empty=True, max_lines=20, max_size=1000
        )

    @Cog.listener()
    async def on_message(self, message: Message) -> None:
        if message.guild and message.guild.id != settings.ASLPP_GUILD_ID:
            return
        if message.channel.id == settings.ASLPP_INTRODUCTIONS_CHANNEL_ID:
            if await store.has_aslpp_intro(message.author.id):
                logger.debug(f"{message.author.id} already has intro")
            else:
                logger.info(f"storing intro record {message.id}")
                await store.add_aslpp_intro(
                    message_id=message.id,
                    user_id=message.author.id,
                    posted_at=message.created_at,
                )

    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member) -> None:
        if after.guild.id != settings.ASLPP_GUILD_ID:
            return
        before_role_ids = {role.id for role in before.roles}
        after_role_ids = {role.id for role in after.roles}
        added_role_ids = after_role_ids - before_role_ids
        removed_role_ids = before_role_ids - after_role_ids
        if settings.ASLPP_ACKNOWLEDGED_RULES_ROLE_ID in added_role_ids:
            logger.info(f"aslpp member acknowledged rules. storing member {after.id}")
            await store.add_aslpp_member(user_id=after.id, joined_at=after.joined_at)
        elif settings.ASLPP_ACKNOWLEDGED_RULES_ROLE_ID in removed_role_ids:
            logger.info(
                f"aslpp member acknowledged rules role removed. removing member {after.id}"
            )
            await store.remove_aslpp_member(user_id=after.id)


def setup(bot: Bot) -> None:
    bot.add_cog(AslPracticePartners(bot))
