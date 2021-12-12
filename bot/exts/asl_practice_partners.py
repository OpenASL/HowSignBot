import asyncio
import datetime as dt
import logging
from contextlib import suppress
from typing import Mapping
from typing import Sequence

import discord
from discord import Color
from discord import Embed
from discord import Guild
from discord import Member
from discord import Message
from discord import VoiceState
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
UNMUTE_WARNING = (
    "⚠️ You're unmuted in a practice room VC. To maximize inclusivity and learning for all members, "
    "we encourage you to keep your voice off during practice. "
    "🤐 You can use the text channels to type responses when needed."
)
DAILY_MESSAGE_TIME = dt.time(8, 0)  # Eastern time
DAILY_MEMBER_KICK_TIME = dt.time(12, 0)  # Eastern time
PRUNE_DAYS = 7


def get_next_task_execution_datetime(time_in_eastern: dt.time) -> dt.datetime:
    """Get next execution time for a daily task.

    Returns an eastern-localized datetime.
    """
    now_eastern = dt.datetime.now(EASTERN)
    date = now_eastern.date()
    if now_eastern.time() > time_in_eastern:
        date = now_eastern.date() + dt.timedelta(days=1)
    return EASTERN.localize(dt.datetime.combine(date, time_in_eastern))


def get_gsheet():
    client = get_gsheet_client()
    return client.open_by_key(settings.ASLPP_SHEET_KEY)


def get_sheet_content(worksheet_name: str) -> list[str]:
    sheet = get_gsheet()
    worksheet = sheet.worksheet(worksheet_name)
    # Get all content from first column
    return worksheet.col_values(1)


MAX_NO_INTRO_USERS_TO_DISPLAY = 30


async def make_no_intros_embed():
    members_without_intro = await store.get_aslpp_members_without_intro(
        since=dt.timedelta(days=settings.ASLPP_INACTIVE_DAYS + 1)
    )

    if len(members_without_intro):
        description = "Here are the oldest memberships:\n"
        description += "\n".join(
            tuple(
                f"<@!{member['user_id']}> - Member for {(utcnow() - member['joined_at']).days} days"
                for member in members_without_intro[:MAX_NO_INTRO_USERS_TO_DISPLAY]
            )
        )
    else:
        description = "✨ _No members to review_"

    embed = Embed(
        title=f"{len(members_without_intro)} members joined > {settings.ASLPP_INACTIVE_DAYS} days ago, acknowledged the rules, and have not posted an intro",
        description=description,
        color=Color.orange(),
    )
    embed.set_footer(
        text=f"These members will automatically be kicked at noon Eastern time. Use {COMMAND_PREFIX}aslpp active <members> to prevent members from getting kicked.\n"
        f"Members who have not logged on in {PRUNE_DAYS} days and have no roles will also be pruned."
    )
    return embed


def get_tags():
    logger.info("fetching tags")
    sheet = get_gsheet()
    worksheet = sheet.worksheet("tags")
    return {
        tag.lower(): {"title": title, "description": content}
        for tags, title, content in worksheet.get_all_values()[1:]  # first row is header
        for tag in tags.split()
    }


def format_role_table(data: Sequence[tuple[str, int]], member_count: int) -> str:
    longest_label_length = max(len(label) for label, _ in data)
    return "\n".join(
        [
            f"{label.rjust(longest_label_length)} ▏ {count:#2d} | {round(count / member_count * 100)}%"
            for label, count in data
        ]
    )


def make_role_table(guild: Guild, label: str, role_ids: Sequence[int]) -> str:
    data = []
    for role_id in role_ids:
        role = guild.get_role(role_id)
        if not role:
            continue
        data.append((role.name, len(role.members)))
    table = format_role_table(data, guild.member_count)
    return f"```\n{label.upper()}\n{table}\n```"


class AslPracticePartners(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tags: dict[str, dict[str, str]] = {}
        self.unmute_warnings: dict[int, dt.datetime] = {}

    def cog_check(self, ctx: Context):
        if not bool(ctx.guild) or ctx.guild.id != settings.ASLPP_GUILD_ID:
            raise commands.errors.CheckFailure(
                f"⚠️ `{COMMAND_PREFIX}{ctx.invoked_with}` must be run within the ASL Practice Partners server (not a DM)."
            )
        return True

    @group(
        name="tag",
        aliases=("tags", "t"),
        invoke_without_command=True,
        hidden=True,
        help="Display a tag or the list of available tags",
    )
    async def tag_group(self, ctx: Context, *, tag_name: str | None):
        if not tag_name:
            await self.display_tags(ctx)
            return
        tag_name = tag_name.lower()
        if tag_name not in self.tags:
            suggestion: str | None = did_you_mean(tag_name, tuple(self.tags.keys()))
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
        self, ctx: Context, targets: commands.Greedy[TextChannel | Member]
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

    async def _kick_inactive(
        self,
        ctx: Context | TextChannel,
        *,
        members_without_intro: list[Mapping],
    ):
        num_kicked = 0
        guild = ctx.guild
        for member_record in members_without_intro[:MAX_NO_INTRO_USERS_TO_DISPLAY]:
            user_id = member_record["user_id"]
            member = guild.get_member(user_id)
            if not member:
                continue
            with suppress(discord.errors.Forbidden):  # user may not allow DMs from bot
                await member.send(KICK_MESSAGE)
            logger.info(f"kicking member {member.id}")
            await guild.kick(member, reason="Inactivity")
            num_kicked += 1
        logger.info(
            f"pruning members who have not logged on in {PRUNE_DAYS} days and have no roles"
        )
        num_pruned = await guild.prune_members(days=PRUNE_DAYS)
        total_kicked = num_kicked + num_pruned
        return total_kicked

    @aslpp_group.command(name="kickall", hidden=True)
    @commands.has_permissions(kick_members=True)
    async def kickall_command(self, ctx: Context):
        members_without_intro = await store.get_aslpp_members_without_intro(
            since=dt.timedelta(days=settings.ASLPP_INACTIVE_DAYS + 1)
        )
        n_members_to_prune = await ctx.guild.estimate_pruned_members(days=PRUNE_DAYS)
        if not len(members_without_intro) and not n_members_to_prune:
            await ctx.send("✨ _No members to kick_")
            return
        num_kicked = await self._kick_inactive(
            ctx, members_without_intro=members_without_intro
        )
        await ctx.reply(f"Kicked {num_kicked} members.")

    @group(
        name="rolestats",
        aliases=("rs",),
        invoke_without_command=True,
        hidden=True,
        doc="Show graphs of role member counts",
    )
    @commands.has_permissions(kick_members=True)  # Staff
    async def role_table_group(self, ctx: Context):
        await ctx.channel.trigger_typing()
        await ctx.send(content=self.make_role_table_skill(ctx.guild))
        await ctx.send(content=self.make_role_table_hearing_spectrum(ctx.guild))
        await ctx.send(content=self.make_role_table_age(ctx.guild))

    def make_role_table_skill(self, guild: Guild):
        return make_role_table(guild, "Skill", settings.ASLPP_SKILL_ROLE_IDS)

    @role_table_group.command("skill", hidden=True)
    @commands.has_permissions(kick_members=True)  # Staff
    async def role_table_skill(self, ctx: Context):
        await ctx.channel.trigger_typing()
        await ctx.reply(content=self.make_role_table_skill(ctx.guild))

    def make_role_table_hearing_spectrum(self, guild: Guild):
        return make_role_table(
            guild, "Hearing Spectrum", settings.ASLPP_HEARING_SPECTRUM_ROLE_IDS
        )

    @role_table_group.command("hearingspectrum", hidden=True)
    @commands.has_permissions(kick_members=True)  # Staff
    async def role_table_hearing_spectrum(self, ctx: Context):
        await ctx.channel.trigger_typing()
        await ctx.reply(content=self.make_role_table_hearing_spectrum(ctx.build))

    def make_role_table_age(self, guild: Guild):
        return make_role_table(guild, "Age", settings.ASLPP_AGE_ROLE_IDS)

    @role_table_group.command("age", hidden=True)
    @commands.has_permissions(kick_members=True)  # Staff
    async def role_table_age(self, ctx: Context):
        await ctx.channel.trigger_typing()
        await ctx.reply(content=self.make_role_table_age(ctx.guild))

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
    async def on_voice_state_update(
        self, member: Member, before: VoiceState, after: VoiceState
    ) -> None:
        if member.guild.id != settings.ASLPP_GUILD_ID:
            return
        if not settings.ASLPP_ENABLE_UNMUTE_WARNING:
            return
        if after.channel is None:  # member left VC
            return
        if not after.self_mute:  # member unmuted
            # Send warning iff it hasn't been sent to the member in the past hour
            if member.id in self.unmute_warnings:
                last_sent = self.unmute_warnings[member.id]
                if (utcnow() - last_sent) > dt.timedelta(hours=1):
                    await self._send_unmute_warning(member)
            else:
                await self._send_unmute_warning(member)

    async def _send_unmute_warning(self, member: Member):
        try:
            logger.info(f"sending unmute warning to member {member.id}")
            await member.send(content=UNMUTE_WARNING)
            self.unmute_warnings[member.id] = utcnow()
        except Exception:
            logger.exception(f"could not send unmute warning to member {member.id}")

    @Cog.listener()
    async def on_ready(self):
        self.bot.loop.create_task(self.daily_message())
        self.bot.loop.create_task(self.daily_member_kick())
        self.tags = get_tags()

    async def daily_message(self):
        while True:
            next_execution_time = get_next_task_execution_datetime(DAILY_MESSAGE_TIME)
            logger.info(
                f"aslpp staff daily message will be sent at at {next_execution_time.isoformat()}"
            )
            await discord.utils.sleep_until(
                next_execution_time.astimezone(dt.timezone.utc)
            )
            channel = self.bot.get_channel(settings.ASLPP_BOT_CHANNEL_ID)
            await channel.send(content=self.make_role_table_skill(channel.guild))
            await channel.send(
                content=self.make_role_table_hearing_spectrum(channel.guild)
            )
            await channel.send(content=self.make_role_table_age(channel.guild))
            embed = await make_no_intros_embed()
            await channel.send(embed=embed)
            logger.info("sent aslpp staff daily message")

    async def daily_member_kick(self):
        while True:
            next_execution_time = get_next_task_execution_datetime(DAILY_MEMBER_KICK_TIME)
            logger.info(
                f"aslpp inactive members will be kicked at {next_execution_time.isoformat()}"
            )
            await discord.utils.sleep_until(
                next_execution_time.astimezone(dt.timezone.utc)
            )
            members_without_intro = await store.get_aslpp_members_without_intro(
                since=dt.timedelta(days=settings.ASLPP_INACTIVE_DAYS + 1)
            )
            channel = self.bot.get_channel(settings.ASLPP_BOT_CHANNEL_ID)
            guild: Guild = channel.guild
            n_members_to_prune = await guild.estimate_pruned_members(days=PRUNE_DAYS)
            if not len(members_without_intro) and not bool(n_members_to_prune):
                logger.info("no inactive aslpp members to kick")
                continue
            await channel.send(content="🥾 _Kicking inactive members_...")
            await self._kick_inactive(
                channel, members_without_intro=members_without_intro
            )
            logger.info("cleared aslpp inactive members")


def setup(bot: Bot) -> None:
    bot.add_cog(AslPracticePartners(bot))
