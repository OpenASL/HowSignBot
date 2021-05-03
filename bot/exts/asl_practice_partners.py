import asyncio
import datetime as dt
import logging
from contextlib import suppress
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

import discord
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
from bot.utils import did_you_mean
from bot.utils.datetimes import EASTERN
from bot.utils.datetimes import utcnow
from bot.utils.gsheets import get_gsheet_client

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX
KICK_MESSAGE = """You've been removed from ASL Practice Partners server due to inactivity from your account.
Don't worry, you can re-join (and we'd love to have you back). You can find the invite link here:
<https://aslpractice.partners>
If you decide to re-join, make sure to post an intro so you don't get kicked again.
"""
DAILY_MESSAGE_TIME = dt.time(8, 0)  # Eastern time


def get_gsheet():
    client = get_gsheet_client()
    return client.open_by_key(settings.ASLPP_SHEET_KEY)


def get_sheet_content(worksheet_name: str) -> List[str]:
    sheet = get_gsheet()
    worksheet = sheet.worksheet(worksheet_name)
    # Get all content from first column
    return worksheet.col_values(1)


async def make_no_intros_embed():
    max_to_display = 30
    members_without_intro = await store.get_aslpp_members_without_intro()

    if len(members_without_intro):
        description = "Here are the oldest memberships:\n"
        description += "\n".join(
            tuple(
                f"<@!{member['user_id']}> - Member for {(utcnow() - member['joined_at']).days} days"
                for member in members_without_intro[:max_to_display]
            )
        )
    else:
        description = "✨ _No members to review_"

    embed = Embed(
        title=f"{len(members_without_intro)} members joined > 30 days ago, acknowledged the rules, and have not posted an intro",
        description=description,
        color=Color.orange(),
    )
    embed.set_footer(
        text=f"Use {COMMAND_PREFIX}aslpp kick <members> to kick. Use {COMMAND_PREFIX}aslpp active <members> to mark members as active so they won't show up in this list."
    )
    return embed


def get_tags():
    logger.info("fetching tags")
    sheet = get_gsheet()
    worksheet = sheet.worksheet("tags")
    return {
        tag: {"title": title, "description": content}
        for tags, title, content in worksheet.get_all_values()[1:]  # first row is header
        for tag in tags.split()
    }


class AslPracticePartners(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tags: Dict[str, Dict[str, str]] = {}

    def cog_check(self, ctx: Context):
        if not bool(ctx.guild) or ctx.guild.id != settings.ASLPP_GUILD_ID:
            raise commands.errors.CheckFailure(
                f"⚠️ `{COMMAND_PREFIX}{ctx.invoked_with}` must be run within the ASL Practice Partners server (not a DM)."
            )
        return True

    @group(
        name="tag",
        aliases=("tags",),
        invoke_without_command=True,
        hidden=True,
        help="Display a tag or the list of available tags",
    )
    async def tag_group(self, ctx: Context, *, tag_name: Optional[str]):
        if not tag_name:
            await self.display_tags(ctx)
            return
        if tag_name not in self.tags:
            suggestion: Optional[str] = did_you_mean(tag_name, tuple(self.tags.keys()))
            if not suggestion:
                await ctx.reply(f'⚠️ No tag matching "{tag_name}"')
                return
            else:
                tag_name = suggestion
        await ctx.reply(embed=Embed.from_dict(self.tags[tag_name]))

    @tag_group.command(
        "update",
        aliases=("sync",),
        hidden=True,
        help="Sync the tags with the spreadsheet",
    )
    @commands.has_permissions(kick_members=True)  # Staff
    async def update_tags(self, ctx: Context):
        await ctx.channel.trigger_typing()
        self.tags = get_tags()
        await ctx.reply("✅ Updated tags.")

    async def display_tags(self, ctx: Context):
        embed = Embed(
            title="Tags",
            description="\n".join(sorted(f"**»** {tag}" for tag in self.tags)),
        )
        embed.set_footer(text=f"To show a tag, type {COMMAND_PREFIX}tag <tagname>.")
        await ctx.reply(embed=embed)

    @group(name="aslpp", hidden=True)
    async def aslpp_group(self, ctx: Context):
        pass

    # TODO: Allow mods/admins to use these commands
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
        await store.clear_aslpp_intros()
        async for message in channel.history(limit=None):
            logger.info(f"storing intro record {message.id}")
            await store.add_aslpp_intro(
                message_id=message.id,
                user_id=message.author.id,
                posted_at=message.created_at,
            )

        role = ctx.guild.get_role(settings.ASLPP_ACKNOWLEDGED_RULES_ROLE_ID)
        await store.clear_aslpp_members()
        for member in role.members:
            if member.bot:
                continue
            logger.info(f"storing member {member.id}")
            await store.add_aslpp_member(user_id=member.id, joined_at=member.joined_at)
        logger.info("finished syncing data")
        await ctx.reply("🙌 Synced data")

    @aslpp_group.command(name="nointros", aliases=("nointro",), hidden=True)
    @commands.has_permissions(kick_members=True)
    async def no_intros_command(self, ctx: Context):
        await ctx.channel.trigger_typing()
        embed = await make_no_intros_embed()
        await ctx.send(embed=embed)

    @aslpp_group.command(name="active", hidden=True)
    @commands.has_permissions(kick_members=True)
    async def active_command(self, ctx: Context, members: commands.Greedy[Member]):
        await store.mark_aslpp_members_active(user_ids=[m.id for m in members])
        await ctx.reply(f"Marked {len(members)} member(s) active.")

    @aslpp_group.command(name="inactive", hidden=True)
    @commands.has_permissions(kick_members=True)
    async def inactive_command(self, ctx: Context, members: commands.Greedy[Member]):
        await store.mark_aslpp_members_inactive(user_ids=[m.id for m in members])
        await ctx.reply(f"Marked {len(members)} member(s) inactive.")

    @aslpp_group.command(name="kick", hidden=True)
    @commands.has_permissions(kick_members=True)
    async def kick_command(
        self, ctx: Context, targets: commands.Greedy[Union[TextChannel, Member]]
    ):
        num_kicked = 0
        for target in targets:
            with suppress(discord.errors.Forbidden):  # user may not allow DMs from bot
                await target.send(KICK_MESSAGE)
            if isinstance(target, Member):
                logger.info(f"kicking member {target.id}")
                await ctx.guild.kick(target, reason="Inactivity")
                num_kicked += 1

        await ctx.reply(f"Kicked {num_kicked} members.")

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
    async def on_member_remove(self, member: Member) -> None:
        if member.guild.id != settings.ASLPP_GUILD_ID:
            return
        logger.info(f"removing data for aslpp member {member.id}")
        await store.remove_aslpp_member(user_id=member.id)

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

    @Cog.listener()
    async def on_ready(self):
        self.bot.loop.create_task(self.daily_message())
        self.tags = get_tags()

    async def daily_message(self):
        while True:
            now_eastern = dt.datetime.now(EASTERN)
            date = now_eastern.date()
            if now_eastern.time() > DAILY_MESSAGE_TIME:
                date = now_eastern.date() + dt.timedelta(days=1)
            then = EASTERN.localize(dt.datetime.combine(date, DAILY_MESSAGE_TIME))
            logger.info(
                f"aslpp inactive members message will be sent at at {then.isoformat()}"
            )
            await discord.utils.sleep_until(then.astimezone(dt.timezone.utc))
            channel = self.bot.get_channel(settings.ASLPP_BOT_CHANNEL_ID)
            embed = await make_no_intros_embed()
            await channel.send(embed=embed)
            logger.info("sent aslpp inactive members message")


def setup(bot: Bot) -> None:
    bot.add_cog(AslPracticePartners(bot))
