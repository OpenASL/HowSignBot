from __future__ import annotations

import asyncio
import datetime as dt
import logging
from contextlib import suppress
from textwrap import dedent
from typing import Mapping, NamedTuple, Sequence, cast

import disnake
from disnake import Embed, Guild, GuildCommandInteraction, Member, Message, VoiceState
from disnake.channel import TextChannel
from disnake.ext import commands
from disnake.ext.commands import Bot, Cog, Context, group, is_owner, slash_command
from disnake.types.embed import Embed as EmbedData

from bot import settings
from bot.database import store
from bot.utils import did_you_mean, get_close_matches
from bot.utils.datetimes import utcnow
from bot.utils.discord import THEME_COLOR, display_name
from bot.utils.gsheets import get_gsheet_client
from bot.utils.tasks import daily_task
from bot.utils.ui import LinkView

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX
KICK_MESSAGE = """You've been kicked from Sign Cafe server due to inactivity from your account.
Don't worry, you can re-join (and we'd love to have you back). You can find the invite link here:
<https://signcafe.chat>
If you decide to re-join, make sure to post an intro so you don't get kicked again.
"""
UNMUTE_WARNING = (
    "⚠️ You're unmuted in a VC. To maximize inclusivity and learning for all members, "
    "we encourage you to keep your voice off during sessions. "
    "🤐 You can use the text channels to type responses when needed."
)
DAILY_MESSAGE_TIME = dt.time(8, 0)  # Eastern time
DAILY_MEMBER_KICK_TIME = dt.time(12, 0)  # Eastern time
PRUNE_DAYS = settings.SIGN_CAFE_PRUNE_DAYS


def get_gsheet():
    client = get_gsheet_client()
    return client.open_by_key(settings.SIGN_CAFE_SHEET_KEY)


def get_sheet_content(worksheet_name: str) -> list[str]:
    sheet = get_gsheet()
    worksheet = sheet.worksheet(worksheet_name)
    # Get all content from first column
    return worksheet.col_values(1)


def get_skill_roles() -> list[disnake.Object]:
    return [disnake.Object(id=role_id) for role_id in settings.SIGN_CAFE_SKILL_ROLE_IDS]


MAX_NO_INTRO_USERS_TO_DISPLAY = 30


class InactiveMemberInfo(NamedTuple):
    members_without_intro: list[Mapping]
    members_with_no_roles: list[Mapping]
    n_members_to_prune: int


async def get_inactive_user_info(guild: Guild) -> InactiveMemberInfo:
    members_without_intro = await store.get_sign_cafe_members_without_intro(
        since=dt.timedelta(days=settings.SIGN_CAFE_INACTIVE_DAYS + 1)
    )
    members_with_no_roles = await store.get_sign_cafe_members_with_no_roles(
        leeway=dt.timedelta(days=PRUNE_DAYS)
    )
    n_members_to_prune = await guild.estimate_pruned_members(
        days=PRUNE_DAYS, roles=get_skill_roles()
    )
    return InactiveMemberInfo(
        members_without_intro=members_without_intro,
        members_with_no_roles=members_with_no_roles,
        n_members_to_prune=n_members_to_prune,
    )


async def make_inactive_members_embed(guild: Guild):
    (
        members_without_intro,
        members_with_no_roles,
        n_members_to_prune,
    ) = await get_inactive_user_info(guild)
    if len(members_without_intro):
        description = "\n".join(
            tuple(
                f"<@!{member['user_id']}> - Member for {(utcnow() - member['joined_at']).days} days"
                for member in members_without_intro[:MAX_NO_INTRO_USERS_TO_DISPLAY]
            )
        )
    else:
        description = "✨ _No members to review_"

    embed = Embed(
        title=f"{len(members_without_intro)} members joined > {settings.SIGN_CAFE_INACTIVE_DAYS} days ago, acknowledged the rules, and have not posted an intro",
        description=description,
        color=THEME_COLOR,
    )
    embed.set_footer(
        text=f"These members will automatically be kicked at noon Eastern time. Use {COMMAND_PREFIX}signcafe active <members> to prevent members from getting kicked.\n"
        f"Members who haven't had channel access for {PRUNE_DAYS} days will also be pruned (estimate: {n_members_to_prune + len(members_with_no_roles)})."
    )
    return embed


def get_tags() -> dict[str, EmbedData]:
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


class SignCafe(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tags: dict[str, EmbedData] = {}
        self.unmute_warnings: dict[int, dt.datetime] = {}

    def cog_check(self, ctx: Context):
        if not bool(ctx.guild) or ctx.guild.id != settings.SIGN_CAFE_GUILD_ID:
            raise commands.errors.CheckFailure(
                f"⚠️ `{COMMAND_PREFIX}{ctx.invoked_with}` must be run within the Sign Cafe server (not a DM)."
            )
        return True

    @slash_command(name="tag", guild_ids=(settings.SIGN_CAFE_GUILD_ID,))
    async def tag_command(self, inter: GuildCommandInteraction):
        pass

    @tag_command.sub_command(name="show")
    async def tag_show(self, inter: GuildCommandInteraction, name: str):
        """Display a tag (response to common question)

        Parameters
        ----------
        name: The tag to show
        """
        await inter.response.send_message(**self._tag_impl(name))

    @tag_show.autocomplete("name")
    async def tag_autocomplete(self, inter: GuildCommandInteraction, tag: str):
        tag = tag.strip().lower()
        options = tuple(self.tags.keys())
        if not tag:
            return sorted(options)[:25]
        return get_close_matches(tag, options)

    @tag_command.sub_command(name="sync")
    @commands.has_permissions(kick_members=True)  # Staff
    async def tag_sync(self, inter: GuildCommandInteraction):
        """(Authorized users only) Get tags list up to date"""
        await inter.response.send_message(**self._tag_sync_impl(), ephemeral=True)

    @tag_command.sub_command(name="edit")
    @commands.has_permissions(kick_members=True)  # Staff
    async def tag_edit(self, inter: GuildCommandInteraction):
        """(Authorized users only) Edit tags"""
        url = (
            f"https://docs.google.com/spreadsheets/d/{settings.SIGN_CAFE_SHEET_KEY}/edit"
        )
        await inter.send(
            "Go to the Google Sheets link below to edit tags.",
            view=LinkView(label="Google Sheets Link", url=url),
            ephemeral=True,
        )

    @tag_command.sub_command(name="list")
    async def tag_list(self, inter: GuildCommandInteraction):
        """List available tags"""
        await inter.response.send_message(**self._tag_list_impl())

    # DEPRECATED TAG COMMANDS

    @group(
        name="tag",
        aliases=("tags", "t"),
        invoke_without_command=True,
        hidden=True,
        help="Display a tag or the list of available tags",
    )
    async def tag_group(self, ctx: Context, *, tag_name: str = ""):
        if not tag_name:
            await ctx.reply(**self._tag_list_impl())
            return
        await ctx.reply(**self._tag_impl(tag_name))

    @tag_group.command(
        "update",
        aliases=("sync",),
        hidden=True,
        help="Sync the tags with the spreadsheet",
    )
    @commands.has_permissions(kick_members=True)  # Staff
    async def update_tags(self, ctx: Context):
        await ctx.channel.trigger_typing()
        await ctx.reply(**self._tag_sync_impl())

    # END DEPRECATED TAG COMMANDS

    def _tag_impl(self, name: str) -> dict:
        name = name.lower()
        if name not in self.tags:
            suggestion: str | None = did_you_mean(name, tuple(self.tags.keys()))
            if not suggestion:
                return {"content": f'⚠️ No tag matching "{name}"'}
            else:
                name = suggestion
        return {"embed": Embed.from_dict(self.tags[name])}

    def _tag_sync_impl(self) -> dict:
        self.tags = get_tags()
        return {"content": "✅ Updated tags."}

    def _tag_list_impl(self) -> dict:
        embed = Embed(
            title="Tags",
            description="\n".join(sorted(f"**»** {tag}" for tag in self.tags)),
        )
        embed.set_footer(text="To show a tag, type /tag show <name>.")
        return {"embed": embed}

    @group(name="signcafe", hidden=True)
    async def sign_cafe_group(self, ctx: Context):
        pass

    # TODO: Allow mods/admins to use these commands
    @sign_cafe_group.command(name="faq", hidden=True)
    @is_owner()
    async def faq_command(self, ctx: Context, channel: TextChannel):
        await ctx.channel.trigger_typing()
        for content in get_sheet_content("faq"):
            await channel.send(content)
            # Sleep to ensure messages are always displayed in the correct order
            await asyncio.sleep(1)
        await ctx.reply("🙌 FAQ posted")

    @sign_cafe_group.command(name="rules", hidden=True)
    @is_owner()
    async def rules_command(self, ctx: Context, channel: TextChannel):
        await ctx.channel.trigger_typing()
        for content in get_sheet_content("rules"):
            await channel.send(content)
            # Sleep to ensure messages are always displayed in the correct order
            await asyncio.sleep(1)
        await ctx.reply("🙌 Rules posted")

    @sign_cafe_group.command(name="welcome", hidden=True)
    @is_owner()
    async def welcome_command(self, ctx: Context, channel: TextChannel):
        await ctx.channel.trigger_typing()
        for content in get_sheet_content("welcome"):
            await channel.send(content)
            # Sleep to ensure messages are always displayed in the correct order
            await asyncio.sleep(1)
        await ctx.reply("🙌 Welcome message posted")

    @sign_cafe_group.command(name="video", hidden=True)
    @is_owner()
    async def video_command(self, ctx: Context, channel: TextChannel):
        await ctx.channel.trigger_typing()
        for content in get_sheet_content("video-etiquette"):
            await channel.send(content)
            # Sleep to ensure messages are always displayed in the correct order
            await asyncio.sleep(1)
        await ctx.reply("🙌 Video etiquette message posted")

    @slash_command(
        name="syncdata",
        guild_ids=(settings.SIGN_CAFE_GUILD_ID,),
    )
    @is_owner()
    async def sync_data_command(
        self, inter: GuildCommandInteraction, intros: bool = False
    ):
        await inter.send("Syncing data…", ephemeral=True)
        if intros:
            channel = cast(
                TextChannel,
                self.bot.get_channel(settings.SIGN_CAFE_INTRODUCTIONS_CHANNEL_ID),
            )
            await store.clear_sign_cafe_intros()
            async for message in channel.history(limit=None):
                logger.info(f"storing intro record {message.id}")
                await store.add_sign_cafe_intro(
                    message_id=message.id,
                    user_id=message.author.id,
                    posted_at=message.created_at,
                )

        role = inter.guild.get_role(settings.SIGN_CAFE_ACKNOWLEDGED_RULES_ROLE_ID)
        assert role is not None
        logger.info("fetching guild")
        guild = await self.bot.fetch_guild(settings.SIGN_CAFE_GUILD_ID)
        await store.clear_sign_cafe_members()
        async for member in guild.fetch_members(limit=10000):
            if member.bot:
                continue
            logger.info(f"storing member {member.id}")
            await store.upsert_sign_cafe_member(member=member)
        logger.info("finished syncing data")
        await inter.send("🙌 Synced data", ephemeral=True)

    @sign_cafe_group.command(name="listinactive", aliases=("nointro",), hidden=True)
    @commands.has_permissions(kick_members=True)
    async def list_inactive_command(self, ctx: Context):
        await ctx.channel.trigger_typing()
        assert ctx.guild is not None
        embed = await make_inactive_members_embed(guild=ctx.guild)
        await ctx.send(embed=embed)

    @sign_cafe_group.command(name="active", hidden=True)
    @commands.has_permissions(kick_members=True)
    async def active_command(self, ctx: Context, members: commands.Greedy[Member]):
        await store.mark_sign_cafe_members_active(user_ids=[m.id for m in members])
        await ctx.reply(f"Marked {len(members)} member(s) active.")

    @sign_cafe_group.command(name="inactive", hidden=True)
    @commands.has_permissions(kick_members=True)
    async def inactive_command(self, ctx: Context, members: commands.Greedy[Member]):
        await store.mark_sign_cafe_members_inactive(user_ids=[m.id for m in members])
        await ctx.reply(f"Marked {len(members)} member(s) inactive.")

    @sign_cafe_group.command(name="kick", hidden=True)
    @commands.has_permissions(kick_members=True)
    async def kick_command(self, ctx: Context, targets: commands.Greedy[Member]):
        num_kicked = 0
        assert ctx.guild is not None
        for target in targets:
            with suppress(disnake.errors.Forbidden):  # user may not allow DMs from bot
                await target.send(KICK_MESSAGE)
            logger.info(f"kicking member {target.id}")
            await ctx.guild.kick(target, reason="Inactivity")
            num_kicked += 1

        await ctx.reply(f"Kicked {num_kicked} members.")

    async def _kick_inactive(
        self,
        ctx: Context | TextChannel,
        *,
        send_message_if_no_inactive_members: bool = False,
    ):
        assert ctx.guild is not None
        (
            members_without_intro,
            members_with_no_roles,
            n_members_to_prune,
        ) = await get_inactive_user_info(ctx.guild)

        if not any(
            (
                len(members_without_intro),
                len(members_with_no_roles),
                bool(n_members_to_prune),
            )
        ):
            logger.debug("no inactive sign_cafe members to kick")
            if send_message_if_no_inactive_members:
                await ctx.send("✨ _No members to kick_")
            return
        num_kicked = 0
        guild = ctx.guild

        logger.info(
            f"kicking members who have not posted an intro in {settings.SIGN_CAFE_INACTIVE_DAYS} days"
        )
        for member_record in members_without_intro[:MAX_NO_INTRO_USERS_TO_DISPLAY]:
            user_id = member_record["user_id"]
            member = await guild.get_or_fetch_member(user_id)
            if not member:
                logging.warn(f"member {user_id} not found")
                continue
            with suppress(disnake.errors.Forbidden):  # user may not allow DMs from bot
                await member.send(KICK_MESSAGE)
            logger.info(f"kicking member {member.id}")
            await guild.kick(
                member,
                reason=f"Inactivity (no intro in {settings.SIGN_CAFE_INACTIVE_DAYS} days)",
            )
            num_kicked += 1

        logger.info(f"kicking members who have had no roles for {PRUNE_DAYS} days")
        for member_record in members_with_no_roles:
            user_id = member_record["user_id"]
            member = await guild.get_or_fetch_member(user_id)
            if not member:
                logging.warn(f"member {user_id} not found")
                continue
            # Paranoid check. NOTE: all members will have the @everyone role
            if len(member.roles) > 1:
                continue
            logger.info(f"kicking member {member.id}")
            await guild.kick(member, reason="Inactivity (no roles=no channel access)")
            num_kicked += 1

        logger.info(
            f"pruning members who have not logged on in {PRUNE_DAYS} days and have only skill roles"
        )
        num_pruned = await guild.prune_members(days=PRUNE_DAYS, roles=get_skill_roles())
        if num_pruned is None:
            num_pruned = 0
        total_kicked = num_kicked + num_pruned
        return total_kicked

    @sign_cafe_group.command(name="kickinactive", hidden=True)
    @commands.has_permissions(kick_members=True)
    async def kick_inactive_command(self, ctx: Context):
        await ctx.channel.trigger_typing()
        num_kicked = await self._kick_inactive(
            ctx, send_message_if_no_inactive_members=True
        )
        if num_kicked:
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
        assert ctx.guild is not None
        await ctx.channel.trigger_typing()
        await ctx.send(content=self.make_role_table_skill(ctx.guild))
        await ctx.send(content=self.make_role_table_hearing_spectrum(ctx.guild))
        await ctx.send(content=self.make_role_table_age(ctx.guild))

    def make_role_table_skill(self, guild: Guild):
        return make_role_table(guild, "Skill", settings.SIGN_CAFE_SKILL_ROLE_IDS)

    def make_role_table_hearing_spectrum(self, guild: Guild):
        return make_role_table(
            guild, "Hearing Spectrum", settings.SIGN_CAFE_HEARING_SPECTRUM_ROLE_IDS
        )

    def make_role_table_age(self, guild: Guild):
        return make_role_table(guild, "Age", settings.SIGN_CAFE_AGE_ROLE_IDS)

    @Cog.listener()
    async def on_message(self, message: Message) -> None:
        if message.guild and message.guild.id != settings.SIGN_CAFE_GUILD_ID:
            return
        # Store when introductions were posted, for autokick functionality
        if message.channel.id == settings.SIGN_CAFE_INTRODUCTIONS_CHANNEL_ID:
            if await store.has_sign_cafe_intro(message.author.id):
                logger.debug(f"{message.author.id} already has intro")
            else:
                logger.info(f"storing intro record {message.id}")
                await store.add_sign_cafe_intro(
                    message_id=message.id,
                    user_id=message.author.id,
                    posted_at=message.created_at,
                )
        # Suggest using /top instead of -topic
        if message.content.strip() == "-topic":
            with suppress(disnake.errors.Forbidden):
                embed = disnake.Embed(
                    title="💡 Tip",
                    description=dedent(
                        f"""I noticed you used the `-topic` command [here]({message.jump_url}).
                    Next time, try using `/top`. It has more topics and uses threads! 👍
                    Before: `-topic`
                    After: `/top`""",
                    ),
                    color=disnake.Color.yellow(),
                )
                await message.author.send(embed=embed)
        # Autothreading
        if message.channel.id in settings.SIGN_CAFE_AUTOTHREAD_CHANNEL_IDS:
            await message.create_thread(
                name=f"{display_name(message.author)} - {message.created_at:%H·%M %b %d}",
                auto_archive_duration=disnake.ThreadArchiveDuration.day,
            )

    @Cog.listener()
    async def on_member_remove(self, member: Member) -> None:
        if member.guild.id != settings.SIGN_CAFE_GUILD_ID:
            return
        logger.info(f"removing data for sign cafe member {member.id}")
        await store.remove_sign_cafe_member(user_id=member.id)

    @Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        if member.guild.id != settings.SIGN_CAFE_GUILD_ID:
            return
        logger.info(f"adding data for new sign cafe member {member.id}")
        await store.upsert_sign_cafe_member(member=member)

    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member) -> None:
        if after.guild.id != settings.SIGN_CAFE_GUILD_ID:
            return
        await store.upsert_sign_cafe_member(member=after)

    @Cog.listener()
    async def on_voice_state_update(
        self, member: Member, before: VoiceState, after: VoiceState
    ) -> None:
        if member.guild.id != settings.SIGN_CAFE_GUILD_ID:
            return
        if not settings.SIGN_CAFE_ENABLE_UNMUTE_WARNING:
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
        self.tags = get_tags() if settings.SIGN_CAFE_SYNC_TAGS else {}

    async def daily_message(self):
        async with daily_task(DAILY_MESSAGE_TIME, name="sign cafe staff message"):
            channel = cast(
                TextChannel, self.bot.get_channel(settings.SIGN_CAFE_BOT_CHANNEL_ID)
            )
            # Fetch all members and add them to the cache
            # This is necessary because we disable chunking guilds at startup
            await channel.guild.chunk(cache=True)
            await channel.send(content=self.make_role_table_skill(channel.guild))
            await channel.send(
                content=self.make_role_table_hearing_spectrum(channel.guild)
            )
            await channel.send(content=self.make_role_table_age(channel.guild))
            embed = await make_inactive_members_embed(guild=channel.guild)
            await channel.send(embed=embed)

    async def daily_member_kick(self):
        async with daily_task(
            DAILY_MEMBER_KICK_TIME, name="sign cafe inactive member pruning"
        ):
            channel = cast(
                TextChannel, self.bot.get_channel(settings.SIGN_CAFE_BOT_CHANNEL_ID)
            )
            (
                members_without_intro,
                members_with_no_roles,
                n_members_to_prune,
            ) = await get_inactive_user_info(channel.guild)
            if any(
                (
                    len(members_without_intro),
                    len(members_with_no_roles),
                    bool(n_members_to_prune),
                )
            ):
                await channel.send(content="🥾 _Kicking inactive members_...")
                await self._kick_inactive(channel)


def setup(bot: Bot) -> None:
    bot.add_cog(SignCafe(bot))
