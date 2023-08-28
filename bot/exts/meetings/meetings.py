import asyncio
import logging
from enum import Enum, auto
from typing import List, Optional, Union, cast

import disnake
import meetings
from disnake import ApplicationCommandInteraction, GuildCommandInteraction
from disnake.ext.commands import (
    Bot,
    Cog,
    Context,
    Param,
    check,
    command,
    errors,
    group,
    is_owner,
    slash_command,
)

from bot import settings
from bot.database import store
from bot.utils.deprecation import send_deprecation_notice
from bot.utils.reactions import (
    STOP_SIGN,
    add_stop_sign,
    get_reaction_message,
    handle_close_reaction,
    maybe_clear_reaction,
    should_handle_reaction,
)
from bot.utils.ui import ButtonGroupOption, ButtonGroupView

from ._zoom import (
    REPOST_EMOJI,
    ZOOM_CLOSED_MESSAGE,
    ZoomCreateError,
    add_repost_after_delay,
    get_zoom_meeting_id,
    is_allowed_zoom_access,
    make_zoom_send_kwargs,
    zoom_client,
    zoom_impl,
)

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX

MEET_CLOSED_MESSAGE = "✨ _Jitsi Meet ended_"
SPEAKEASY_CLOSED_MESSAGE = "✨ _Speakeasy event ended_"
WATCH2GETHER_HELP = """Start a watch2gether session

You can optionally pass a URL to use for the first video.

Examples:
```
{COMMAND_PREFIX}w2g
{COMMAND_PREFIX}w2g https://www.youtube.com/watch?v=DaMjr4AfYA0
```
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)

WATCH2GETHER_CLOSED_MESSAGE = "✨ _watch2gether room closed_"


def make_jitsi_embed(meeting: meetings.JitsiMeet):
    title = f"<{meeting.join_url}>"
    content = (
        f"**Join URL**: <{meeting.join_url}>\n**Desktop App Link***: <{meeting.deeplink}>"
    )
    if meeting.name:
        content = f"{content}\n**Name**: {meeting.name}"
    content = f"{content}\n\n🚀 This meeting is happening now. Go practice!\n*Desktop App Link requires <https://github.com/jitsi/jitsi-meet-electron>\n*After the meeting ends, click {STOP_SIGN} to remove this message.*"
    logger.info("sending jitsi meet info")
    return disnake.Embed(
        title=title,
        description=content,
        color=disnake.Color.blue(),
    )


def make_watch2gether_embed(url: str, video_url: Optional[str]) -> disnake.Embed:
    description = "🚀 Watch videos together!"
    if video_url:
        description += f"\nQueued video: <{video_url}>"
    description += "\n*When finished, react with 🛑 to remove this message.*"
    return disnake.Embed(title=url, description=description, color=disnake.Color.gold())


def make_zoom_standby_embed():
    return disnake.Embed(
        color=disnake.Color.blue(),
        title="✋ Stand By",
        description="Zoom details will be posted here when the meeting is ready to start.",
    )


class ProtectionMode(Enum):
    WAITING_ROOM = auto()
    FS_CAPTCHA = auto()


class Meetings(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @slash_command(name="zoom")
    @check(is_allowed_zoom_access)
    async def zoom_command(self, inter: ApplicationCommandInteraction):
        pass

    @zoom_command.sub_command(name="new")
    async def zoom_new(self, inter: ApplicationCommandInteraction):
        """(Authorized users only) Create a Zoom meeting"""
        assert inter.user is not None
        value = await self._prompt_for_protection_type(inter)
        with_zzzzoom = value == ProtectionMode.FS_CAPTCHA

        async def send_channel_message(mid: int):
            send_kwargs = await make_zoom_send_kwargs(mid, guild_id=inter.guild_id)
            return await inter.channel.send(**send_kwargs)

        await zoom_impl(
            bot=self.bot,
            zoom_user=settings.ZOOM_USERS[inter.user.id],
            channel_id=inter.channel.id,
            meeting_id=None,
            send_channel_message=send_channel_message,
            set_up=True,
            with_zzzzoom=with_zzzzoom,
        )

    @zoom_command.sub_command(name="crosspost")
    async def zoom_crosspost(
        self,
        inter: ApplicationCommandInteraction,
        meeting_id_str: str = Param(name="meeting_id"),
    ):
        """(Authorized users only) Crosspost a previously-created Zoom meeting

        Parameters
        ----------
        meeting_id: Zoom meeting ID or zzzzoom ID
        """
        assert inter.user is not None

        zoom_or_zzzzoom_id: Union[int, str]
        try:
            zoom_or_zzzzoom_id = int(meeting_id_str)
        except ValueError:
            zoom_or_zzzzoom_id = meeting_id_str
            with_zzzzoom = True
        else:
            with_zzzzoom = False

        meeting_id = await get_zoom_meeting_id(zoom_or_zzzzoom_id)
        meeting = await store.get_zoom_meeting(meeting_id)
        if meeting is None:
            await inter.response.edit_message(
                content=f"⚠️ Could not find zoom meeting for {meeting_id_str}."
            )
            return
        set_up = meeting["setup_at"] is not None
        if set_up:

            async def send_channel_message(mid: int):
                send_kwargs = await make_zoom_send_kwargs(mid, guild_id=inter.guild_id)
                return await inter.channel.send(**send_kwargs)

        else:

            async def send_channel_message(mid: int):
                return await inter.channel.send(embed=make_zoom_standby_embed())

        await zoom_impl(
            bot=self.bot,
            zoom_user=settings.ZOOM_USERS[inter.user.id],
            channel_id=inter.channel.id,
            meeting_id=zoom_or_zzzzoom_id,
            send_channel_message=send_channel_message,
            set_up=set_up,
            with_zzzzoom=with_zzzzoom,
        )
        await inter.send("📋 _Crossposted_")

    @zoom_command.sub_command(name="setup")
    async def zoom_setup(self, inter: GuildCommandInteraction):
        """(Authorized users only) Set up a Zoom before revealing its details to other users"""
        assert inter.user is not None
        assert inter.channel_id is not None
        value = await self._prompt_for_protection_type(inter)
        with_zzzzoom = value == ProtectionMode.FS_CAPTCHA

        async def send_channel_message(_):
            return await inter.channel.send(embed=make_zoom_standby_embed())

        meeting_id, _ = await zoom_impl(
            bot=self.bot,
            zoom_user=settings.ZOOM_USERS[inter.user.id],
            channel_id=inter.channel_id,
            meeting_id=None,
            send_channel_message=send_channel_message,
            set_up=False,
            with_zzzzoom=with_zzzzoom,
        )

        zoom_messages = tuple(await store.get_zoom_messages(meeting_id=meeting_id))
        # DM zoom link and instructions once
        if len(zoom_messages) <= 1:
            send_kwargs = await make_zoom_send_kwargs(
                meeting_id, guild_id=None, include_instructions=False
            )
            await inter.user.send(content="🔨 Set up your meeting below", **send_kwargs)
            await inter.user.send(
                "To post in another channel, send the following command in that channel:\n"
                f"```/zoom crosspost {meeting_id}```\n"
                "When you're ready for people to join, reply with:\n"
                f"```/zoom start {meeting_id}```"
            )

    @zoom_command.sub_command(name="start")
    async def zoom_setup_start(
        self,
        inter: ApplicationCommandInteraction,
        meeting_id_str: str = Param(name="meeting_id"),
    ):
        """(Authorized users only) Reveal meeting details for a meeting started with the setup command"""
        zoom_or_zzzzoom_id: Union[int, str]
        try:
            zoom_or_zzzzoom_id = int(meeting_id_str)
        except ValueError:
            zoom_or_zzzzoom_id = meeting_id_str

        meeting_id = await get_zoom_meeting_id(zoom_or_zzzzoom_id)
        meeting_exists = await store.zoom_meeting_exists(meeting_id=meeting_id)
        if not meeting_exists:
            raise errors.CheckFailure(
                f"⚠️ Could not find Zoom meeting with ID {meeting_id_str}. Make sure to run `/zoom setup` first."
            )
        await store.set_up_zoom_meeting(meeting_id=meeting_id)
        zoom_messages = tuple(await store.get_zoom_messages(meeting_id=meeting_id))
        if not zoom_messages:
            raise errors.CheckFailure(f"⚠️ No meeting messages for meeting {meeting_id}.")
        messages: List[disnake.Message] = []
        for message_info in zoom_messages:
            channel_id = message_info["channel_id"]
            message_id = message_info["message_id"]
            channel = cast(disnake.TextChannel, self.bot.get_channel(channel_id))
            assert channel is not None
            message: disnake.Message = await channel.fetch_message(message_id)
            messages.append(message)
            logger.info(
                f"revealing meeting details for meeting {meeting_id} in channel {channel_id}, message {message_id}"
            )
            send_kwargs = await make_zoom_send_kwargs(
                meeting_id=meeting_id,
                guild_id=message.guild.id if message.guild else None,
            )
            await message.edit(**send_kwargs)
            add_repost_after_delay(self.bot, message)
        if inter.guild_id is None:
            assert inter.user is not None
            links = "\n".join(
                f"[{message.guild} - #{message.channel}]({message.jump_url})"
                for message in messages
            )
            await inter.send(
                embed=disnake.Embed(title="🚀 Meeting Details Revealed", description=links)
            )
        else:
            channel_message = next(
                (
                    message
                    for message in messages
                    if message.channel.id == inter.channel_id
                ),
                None,
            )
            if channel_message:
                await inter.send(
                    f"🚀 Meeting details revealed: {channel_message.jump_url}"
                )
            else:
                await inter.send("🚀 Meeting details revealed.", ephemeral=True)

    @zoom_command.sub_command(name="stop")
    async def zoom_stop(
        self,
        inter: ApplicationCommandInteraction,
        meeting_id_str: str = Param(name="meeting_id"),
    ):
        """(Authorized users only) Remove meeting details for a Zoom meeting

        Parameters
        ----------
        meeting_id: Zoom meeting ID or zzzzoom ID
        """
        zoom_or_zzzzoom_id: Union[int, str]
        try:
            zoom_or_zzzzoom_id = int(meeting_id_str)
        except ValueError:
            zoom_or_zzzzoom_id = meeting_id_str

        meeting_id = await get_zoom_meeting_id(zoom_or_zzzzoom_id)
        meeting_exists = await store.zoom_meeting_exists(meeting_id=meeting_id)
        if not meeting_exists:
            raise errors.CheckFailure(
                f"⚠️ Could not find Zoom meeting with ID {meeting_id}. Make sure to run `{COMMAND_PREFIX}zoom setup {meeting_id}` first."
            )
        zoom_messages = tuple(await store.get_zoom_messages(meeting_id=meeting_id))
        if not zoom_messages:
            raise errors.CheckFailure(f"⚠️ No meeting messages for meeting {meeting_id}.")
        messages = []
        for message_info in zoom_messages:
            channel_id = message_info["channel_id"]
            message_id = message_info["message_id"]
            channel = cast(disnake.TextChannel, self.bot.get_channel(channel_id))
            message: disnake.Message = await channel.fetch_message(message_id)
            messages.append(message)
            logger.info(
                f"scrubbing meeting details for meeting {meeting_id} in channel {channel_id}, message {message_id}"
            )
            await message.edit(content=ZOOM_CLOSED_MESSAGE, embed=None, view=None)
            await maybe_clear_reaction(message, REPOST_EMOJI)
        await store.end_zoom_meeting(meeting_id=meeting_id)
        await inter.send("🛑 Meeting details removed.")

    # XXX: Ideally we'd use slash command permissions intead of a check here,
    # but those can only be set per-guild at the moment.
    @zoom_command.sub_command(name="users")
    @is_owner()
    async def zoom_users(self, inter: ApplicationCommandInteraction):
        """(Bot owner only) List users who have access to the zoom commands"""
        try:
            users = await zoom_client.list_zoom_users()
        except asyncio.exceptions.TimeoutError:
            logger.exception("zoom request timed out")
            await inter.send(
                "🚨 _Request to Zoom API timed out. This may be due to rate limiting. Try again later._"
            )
            return
        licensed_user_emails = {
            user.email
            for user in users
            if user.type == meetings.zoom.ZoomPlanType.LICENSED
        }
        description = "\n".join(
            tuple(
                ("👑 " if email.lower() in licensed_user_emails else "") + f"<@!{user_id}>"
                for user_id, email in settings.ZOOM_USERS.items()
            )
        )
        embed = disnake.Embed(
            title=f"Fancy Zoom Users ({len(settings.ZOOM_USERS)})",
            description=description,
            color=disnake.Color.blue(),
        )
        embed.set_footer(text="👑 = Licensed")
        await inter.send(embed=embed)

    @slash_command(name="watch2gether")
    async def watch2gether_command(
        self, inter: ApplicationCommandInteraction, video_url: Optional[str] = None
    ):
        """Start a watch2gether session

        Parameters
        ----------
        video_url: YouTube URL to queue as the first video
        """
        logger.info("creating watch2gether meeting")
        try:
            url = await meetings.create_watch2gether(
                settings.WATCH2GETHER_API_KEY, video_url
            )
        except Exception:
            logger.exception("could not create watch2gether room")
            await inter.send(
                content="🚨 _Could not create watch2gether room. That's embarrassing._"
            )
        else:
            await inter.send(embed=make_watch2gether_embed(url, video_url))

    @slash_command(name="jitsi")
    async def jitsi_command(
        self, inter: ApplicationCommandInteraction, *, name: Optional[str] = None
    ):
        """Start a Jitsi Meet meeting

        Parameters
        ----------
        name: Name of the meeting
        """
        meeting = meetings.create_jitsi_meet(name, secret=settings.SECRET_KEY)
        logger.info("sending jitsi meet info")
        await inter.send(embed=make_jitsi_embed(meeting))
        message = await inter.original_message()
        await add_stop_sign(message)

    @slash_command(name="speakeasy")
    async def speakeasy_command(
        self, inter: ApplicationCommandInteraction, *, name: Optional[str] = None
    ):
        """Start a Speakeasy (https://speakeasy.co/) event

        Parameters
        ----------
        name: Name of the meeting
        """
        join_url = meetings.create_speakeasy(name, secret=settings.SECRET_KEY)
        content = f"️🍻 **Speakeasy**\nJoin URL: <{join_url}>"
        if name:
            content = f"{content}\n**Name**: {name}"
        content = f"{content}\n🚀 This event is happening now. Make a friend!"
        logger.info("sending speakeasy info")
        await inter.send(content=content)
        message = await inter.original_message()
        await add_stop_sign(message)

    # Deprecated prefix commands

    @group(name="zoom", aliases=("z",), invoke_without_command=True)
    @check(is_allowed_zoom_access)
    async def zoom_group(
        self, ctx: Context, meeting_id: Optional[Union[int, str]] = None
    ):
        """AUTHORIZED USERS ONLY: Start a Zoom meeting"""
        await self.zoom_group_impl(ctx, meeting_id=meeting_id, with_zzzzoom=False)

    @group(
        name="zzzzoom",
        aliases=("zzoom", "zzzoom", "zzzzzoom", "zz", "zzz", "zzzz", "zzzzz"),
        invoke_without_command=True,
    )
    @check(is_allowed_zoom_access)
    async def zzzzoom_group(
        self, ctx: Context, meeting_id: Optional[Union[str, int]] = None
    ):
        """AUTHORIZED USERS ONLY: Start a Zoom meeting and display the zzzzoom.us join URL instead of the normal join URL."""
        await self.zoom_group_impl(ctx, meeting_id=meeting_id, with_zzzzoom=True)

    @zoom_command.error
    @zzzzoom_group.error
    @zoom_group.error  # type: ignore
    async def zoom_error(self, ctx, error):
        if isinstance(error, ZoomCreateError):
            logger.error("could not create zoom due to unexpected error", exc_info=error)
            await ctx.send(error)

    async def zoom_group_impl(
        self, ctx: Context, *, meeting_id: Optional[Union[int, str]], with_zzzzoom: bool
    ):
        await ctx.channel.trigger_typing()

        async def send_channel_message(mid: int):
            send_kwargs = await make_zoom_send_kwargs(
                mid, guild_id=ctx.guild.id if ctx.guild else None
            )
            return await ctx.reply(**send_kwargs)

        await zoom_impl(
            bot=self.bot,
            zoom_user=settings.ZOOM_USERS[ctx.author.id],
            channel_id=ctx.channel.id,
            meeting_id=meeting_id,
            send_channel_message=send_channel_message,
            set_up=True,
            with_zzzzoom=with_zzzzoom,
        )

        before_example = f"{COMMAND_PREFIX}{ctx.invoked_with}"
        after_example = "/zoom"
        if meeting_id:
            substitute = "/zoom crosspost"
            before_example += " <meeting id>"
            after_example += " crosspost <meeting id>"
        else:
            substitute = "/zoom create"
            after_example += " create"
        await send_deprecation_notice(
            ctx,
            substitute=substitute,
            before_example=before_example,
            after_example=after_example,
        )

    @command(name="w2g", aliases=("wtg", "watch2gether"), help=WATCH2GETHER_HELP)
    async def watch2gether_prefix_command(
        self, ctx: Context, video_url: Optional[str] = None
    ):
        logger.info("creating watch2gether meeting")
        try:
            url = await meetings.create_watch2gether(
                settings.WATCH2GETHER_API_KEY, video_url
            )
        except Exception:
            logger.exception("could not create watch2gether room")
            message = await ctx.send(
                content="🚨 _Could not create watch2gether room. That's embarrassing._"
            )
        else:
            message = await ctx.send(embed=make_watch2gether_embed(url, video_url))

        await add_stop_sign(message)

    @command(name="meet", aliases=("jitsi",), help="Start a Jitsi Meet meeting")
    async def meet_prefix_command(self, ctx: Context, *, name: Optional[str]):
        meeting = meetings.create_jitsi_meet(name, secret=settings.SECRET_KEY)
        logger.info("sending jitsi meet info")
        message = await ctx.send(embed=make_jitsi_embed(meeting))

        await add_stop_sign(message)

    @command(name="speakeasy", help="Start a Speakeasy (https://speakeasy.co/) event")
    async def speakeasy_prefix_command(self, ctx: Context, *, name: Optional[str]):
        join_url = meetings.create_speakeasy(name, secret=settings.SECRET_KEY)
        content = f"️🍻 **Speakeasy**\nJoin URL: <{join_url}>"
        if name:
            content = f"{content}\n**Name**: {name}"
        content = f"{content}\n🚀 This event is happening now. Make a friend!"
        logger.info("sending speakeasy info")
        message = await ctx.send(content=content)
        await add_stop_sign(message)

    # End deprecated prefix commands

    async def edit_meeting_moved(self, message: disnake.Message) -> None:
        await message.edit(
            content=f"{REPOST_EMOJI} *Meeting details moved below.*",
            embed=None,
            view=None,
        )
        await maybe_clear_reaction(message, REPOST_EMOJI)

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: disnake.RawReactionActionEvent) -> None:
        if should_handle_reaction(self.bot, payload, {REPOST_EMOJI}):
            message = await get_reaction_message(self.bot, payload)
            if not message:
                return
            zoom_message = await store.get_zoom_message(message.id)
            if not zoom_message:
                return
            zoom_meeting = await store.get_zoom_meeting(zoom_message["meeting_id"])
            if not zoom_meeting:
                return
            # Meeting isn't set up, don't reveal it yet
            if not zoom_meeting["setup_at"]:
                return
            original_message = None
            if message.reference:
                if message.reference.cached_message:
                    original_message = message.reference.cached_message
                else:
                    channel = cast(
                        disnake.TextChannel, self.bot.get_channel(message.channel.id)
                    )
                    assert message.reference.message_id is not None
                    original_message = await channel.fetch_message(
                        message.reference.message_id
                    )
            # Try to remove the old message and reply with a new message
            if original_message:
                try:
                    await message.delete()
                except Exception:
                    await self.edit_meeting_moved(message)
            else:
                await self.edit_meeting_moved(message)

            send_method = original_message.reply if original_message else message.reply
            send_kwargs = await make_zoom_send_kwargs(
                zoom_message["meeting_id"],
                guild_id=message.guild.id if message.guild else None,
            )
            new_message = await send_method(
                content="👐 **This meeting is still going**. Come on in!",
                mention_author=False,
                **send_kwargs,
            )
            add_repost_after_delay(self.bot, new_message)

            async with store.transaction():
                await store.create_zoom_message(
                    message_id=new_message.id,
                    channel_id=new_message.channel.id,
                    meeting_id=zoom_message["meeting_id"],
                )
                await store.remove_zoom_message(message_id=zoom_message["message_id"])

            return

        async def close_zoom_message(msg: disnake.Message):
            await store.remove_zoom_message(message_id=msg.id)
            await maybe_clear_reaction(msg, REPOST_EMOJI)
            return ZOOM_CLOSED_MESSAGE

        await handle_close_reaction(
            self.bot,
            payload,
            close_messages={
                r"zoom\.us|Stand By|Could not create Zoom|localhost": close_zoom_message,
                r"meet\.jit\.si": MEET_CLOSED_MESSAGE,
                r"Speakeasy": SPEAKEASY_CLOSED_MESSAGE,
                r"w2g\.tv|Could not create watch2gether": WATCH2GETHER_CLOSED_MESSAGE,
            },
        )

    async def _prompt_for_protection_type(
        self, inter: ApplicationCommandInteraction
    ) -> ProtectionMode:
        assert inter.user is not None
        view = ButtonGroupView.from_options(
            options=(
                ButtonGroupOption(
                    label="FS Captcha", value=ProtectionMode.FS_CAPTCHA, emoji="👌"
                ),
                ButtonGroupOption(
                    label="Waiting Room", value=ProtectionMode.WAITING_ROOM, emoji="🚪"
                ),
            ),
            creator_id=inter.user.id,
            choice_label="🔐 **Protection Mode**",
        )
        await inter.send(
            "🔐 **How do you want to protect the meeting?** Choose one.", view=view
        )
        value = await view.wait_for_value()
        return value or ProtectionMode.FS_CAPTCHA


def setup(bot: Bot) -> None:
    bot.add_cog(Meetings(bot))
