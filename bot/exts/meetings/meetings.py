import asyncio
import logging
from enum import auto
from enum import Enum
from typing import cast
from typing import List
from typing import Optional
from typing import Union

import disnake
from disnake import ApplicationCommandInteraction
from disnake import MessageInteraction
from disnake.ext.commands import Bot
from disnake.ext.commands import check
from disnake.ext.commands import Cog
from disnake.ext.commands import command
from disnake.ext.commands import Context
from disnake.ext.commands import errors
from disnake.ext.commands import group
from disnake.ext.commands import is_owner
from disnake.ext.commands import Param
from disnake.ext.commands import slash_command

import meetings
from ._zoom import add_repost_after_delay
from ._zoom import get_zoom_meeting_id
from ._zoom import is_allowed_zoom_access
from ._zoom import make_zoom_embed
from ._zoom import REPOST_EMOJI
from ._zoom import ZOOM_CLOSED_MESSAGE
from ._zoom import zoom_impl
from ._zoom import ZoomCreateError
from bot import settings
from bot.database import store
from bot.utils.deprecation import send_deprecation_notice
from bot.utils.reactions import add_stop_sign
from bot.utils.reactions import get_reaction_message
from bot.utils.reactions import handle_close_reaction
from bot.utils.reactions import maybe_clear_reaction
from bot.utils.reactions import should_handle_reaction
from bot.utils.reactions import STOP_SIGN
from bot.utils.ui import ButtonGroupOption
from bot.utils.ui import ButtonGroupView
from bot.utils.ui import DropdownView

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
    description += "\n*When finished, click 🛑 to remove this message.*"
    return disnake.Embed(title=url, description=description, color=disnake.Color.gold())


class ProtectionType(Enum):
    WAITING_ROOM = auto()
    FS_CAPTCHA = auto()


class Meetings(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @slash_command(name="zoom")
    @check(is_allowed_zoom_access)
    async def zoom_command(self, inter: ApplicationCommandInteraction):
        pass

    @zoom_command.sub_command(name="create")
    async def zoom_create(self, inter: ApplicationCommandInteraction):
        """(Authorized users only) Create a Zoom meeting"""
        assert inter.user is not None

        view = ButtonGroupView.from_options(
            options=(
                ButtonGroupOption(
                    label="FS Captcha", value=ProtectionType.FS_CAPTCHA, emoji="👌"
                ),
                ButtonGroupOption(
                    label="Waiting Room", value=ProtectionType.WAITING_ROOM, emoji="🚪"
                ),
            ),
            creator_id=inter.user.id,
        )
        await inter.send(
            "🔐 **How do you want to protect the meeting?** Choose one.", view=view
        )
        value = await view.wait_for_value()
        with_zzzzoom = value == ProtectionType.FS_CAPTCHA

        async def send_channel_message(mid: int):
            return await inter.channel.send(embed=await make_zoom_embed(mid))

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
    async def zoom_crosspost(self, inter: ApplicationCommandInteraction, meeting_id: str):
        """Crosspost a previously-created Zoom meeting

        Parameters
        ----------
        meeting_id: Zoom meeting ID or zzzzoom ID
        """
        assert inter.user is not None

        zoom_or_zzzzoom_id: Union[int, str]
        try:
            zoom_or_zzzzoom_id = int(meeting_id)
        except ValueError:
            zoom_or_zzzzoom_id = meeting_id
            with_zzzzoom = True
        else:
            with_zzzzoom = False

        async def send_channel_message(mid: int):
            return await inter.channel.send(embed=await make_zoom_embed(mid))

        await zoom_impl(
            bot=self.bot,
            zoom_user=settings.ZOOM_USERS[inter.user.id],
            channel_id=inter.channel.id,
            meeting_id=zoom_or_zzzzoom_id,
            send_channel_message=send_channel_message,
            set_up=True,
            with_zzzzoom=with_zzzzoom,
        )
        await inter.send("_Crossposted Zoom_")

    @zoom_command.sub_command(name="stop")
    async def zoom_stop(
        self,
        inter: ApplicationCommandInteraction,
        meeting_id_str: str = Param(name="meeting_id"),
    ):
        """Remove meeting details for a Zoom meeting

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
            channel = self.bot.get_channel(channel_id)
            message: disnake.Message = await channel.fetch_message(message_id)
            messages.append(message)
            logger.info(
                f"scrubbing meeting details for meeting {meeting_id} in channel {channel_id}, message {message_id}"
            )
            await message.edit(content=ZOOM_CLOSED_MESSAGE, embed=None)
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
            users = await meetings.list_zoom_users(token=settings.ZOOM_JWT)
        except asyncio.exceptions.TimeoutError:
            logger.exception("zoom request timed out")
            await inter.send(
                "🚨 _Request to Zoom API timed out. This may be due to rate limiting. Try again later._"
            )
            return
        licensed_user_emails = {
            user.email for user in users if user.type == meetings.ZoomPlanType.LICENSED
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

    @zoom_command.sub_command(
        name="license", hidden=True, help="Upgrade a user to the Licensed plan type."
    )
    @is_owner()
    async def zoom_license(
        self,
        inter: ApplicationCommandInteraction,
        user: disnake.User,
    ):
        """(Bot owner only) Upgrade a Zoom user to a Licensed plan"""
        assert inter.user is not None
        if user.id not in settings.ZOOM_USERS:
            await inter.send(f"🚨 _{user.mention} is not a configured Zoom user._")
            return

        await inter.send(
            f"✋ **{user.mention} will be upgraded to a Licensed plan**.",
        )
        zoom_user_id = settings.ZOOM_USERS[user.id]
        try:
            logger.info(f"attempting to upgrade user {user.id} to licensed plan")
            await meetings.update_zoom_user(
                token=settings.ZOOM_JWT,
                user_id=zoom_user_id,
                data={"type": meetings.ZoomPlanType.LICENSED},
            )
        except meetings.MaxZoomLicensesError:
            try:
                users = await meetings.list_zoom_users(token=settings.ZOOM_JWT)
            except asyncio.exceptions.TimeoutError:
                logger.exception("zoom request timed out")
                await inter.send(
                    "🚨 _Request to Zoom API timed out. This may be due to rate limiting. Try again later._"
                )
                return
            zoom_to_discord_user_mapping = {
                email.lower(): disnake_id
                for disnake_id, email in settings.ZOOM_USERS.items()
            }
            # Discord user IDs for Licensed users
            licensed_user_discord_ids = tuple(
                zoom_to_discord_user_mapping[user.email.lower()]
                for user in users
                if user.email.lower() in zoom_to_discord_user_mapping
                and user.type == meetings.ZoomPlanType.LICENSED
                # Don't allow de-licensing the bot owner, of course
                and zoom_to_discord_user_mapping[user.email.lower()] != settings.OWNER_ID
            )
            if len(licensed_user_discord_ids):
                options = [
                    disnake.SelectOption(
                        label=settings.ZOOM_USERS[discord_user_id], value=discord_user_id
                    )
                    for discord_user_id in licensed_user_discord_ids
                ]

                async def on_select(select_interaction: MessageInteraction, value: str):
                    downgraded_user_id = int(value)
                    await select_interaction.response.edit_message(
                        content=f"☑️ Selected <@!{downgraded_user_id}> to downgrade.",
                        view=None,
                    )
                    try:
                        logger.info(
                            f"attempting to downgrade user {downgraded_user_id} to basic plan"
                        )
                        await meetings.update_zoom_user(
                            token=settings.ZOOM_JWT,
                            user_id=settings.ZOOM_USERS[downgraded_user_id],
                            data={"type": meetings.ZoomPlanType.BASIC},
                        )
                    except meetings.ZoomClientError:
                        logger.exception(f"failed to downgrade user {downgraded_user_id}")
                        await inter.send(
                            f"🚨 _Failed to downgrade <@!{downgraded_user_id}>. Check the logs for details._"
                        )
                    try:
                        logger.info(
                            f"re-attempting to upgrade user {user.id} to licensed plan"
                        )
                        await meetings.update_zoom_user(
                            token=settings.ZOOM_JWT,
                            user_id=zoom_user_id,
                            data={"type": meetings.ZoomPlanType.LICENSED},
                        )
                    except meetings.ZoomClientError:
                        logger.exception(f"failed to upgrade user {user.id}")
                        await inter.send(
                            f"🚨 _Failed to upgrade {user.mention}. Check the logs for details._"
                        )
                    await inter.send(
                        f"👑 **{user.mention} successfully upgraded to Licensed plan.**\n<@!{downgraded_user_id}> downgraded to Basic."
                    )

                view = DropdownView.from_options(
                    options=options, on_select=on_select, placeholder="Choose a user"
                )
                await inter.send("Choose a user to downgrade to Basic.", view=view)
            else:
                await inter.send(
                    "🚨 _No available users to downgrade on Discord. Go to the Zoom account settings to manage licenses_."
                )
                return
            return
        except meetings.ZoomClientError as error:
            await inter.send(f"🚨 _{error.args[0]}_")
            return
        except Exception:
            logger.exception(f"failed to license user {user}")
            await inter.send(
                f"🚨 _Failed to license user {user.mention}. Check the logs for details._"
            )
            return
        else:
            await inter.send(f"👑 **{user.mention} upgraded to a Licensed plan**.")

    # Deprecated prefix commands

    @group(name="zoom", aliases=("z",), invoke_without_command=True)
    @check(is_allowed_zoom_access)
    async def zoom_group(
        self, ctx: Context, meeting_id: Optional[Union[int, str]] = None
    ):
        """AUTHORIZED USERS ONLY: Start a Zoom meeting"""
        await self.zoom_group_impl(ctx, meeting_id=meeting_id, with_zzzzoom=False)

    @zoom_group.command(
        name="setup",
        help="Set up a Zoom before revealing its details to other users. Useful for meetings that have breakout rooms.",
    )
    @check(is_allowed_zoom_access)
    async def zoom_setup(
        self, ctx: Context, meeting_id: Optional[Union[int, str]] = None
    ):
        await self.zoom_setup_impl(ctx, meeting_id=meeting_id, with_zzzzoom=False)

    @zoom_group.command(
        name="start",
        help="Reveal meeting details for a meeting started with the setup command",
    )
    @check(is_allowed_zoom_access)
    async def zoom_setup_start(
        self, ctx: Context, meeting_id: Optional[Union[int, str]] = None
    ):
        await ctx.channel.trigger_typing()
        if meeting_id:
            meeting_id = await get_zoom_meeting_id(meeting_id)
            meeting_exists = await store.zoom_meeting_exists(meeting_id=meeting_id)
            if not meeting_exists:
                raise errors.CheckFailure(
                    f"⚠️ Could not find Zoom meeting with ID {meeting_id}. Make sure to run `{COMMAND_PREFIX}zoom setup {meeting_id}` first."
                )
        else:
            zoom_user = settings.ZOOM_USERS[ctx.author.id]
            latest_meeting = await store.get_latest_pending_zoom_meeting_for_user(
                zoom_user
            )
            if not latest_meeting:
                raise errors.CheckFailure(
                    f"⚠️ You do not have any pending Zoom meetings. Make sure to run `{COMMAND_PREFIX}zoom setup [meeting_id]` first."
                )
            meeting_id = cast(int, latest_meeting["meeting_id"])
        await store.set_up_zoom_meeting(meeting_id=meeting_id)
        zoom_messages = tuple(await store.get_zoom_messages(meeting_id=meeting_id))
        if not zoom_messages:
            raise errors.CheckFailure(f"⚠️ No meeting messages for meeting {meeting_id}.")
        embed = await make_zoom_embed(meeting_id=meeting_id)
        messages: List[disnake.Message] = []
        for message_info in zoom_messages:
            channel_id = message_info["channel_id"]
            message_id = message_info["message_id"]
            channel = self.bot.get_channel(channel_id)
            message: disnake.Message = await channel.fetch_message(message_id)
            messages.append(message)
            logger.info(
                f"revealing meeting details for meeting {meeting_id} in channel {channel_id}, message {message_id}"
            )
            await message.edit(embed=embed)
            add_repost_after_delay(self.bot, message)
        if ctx.guild is None:
            links = "\n".join(
                f"[{message.guild} - #{message.channel}]({message.jump_url})"
                for message in messages
            )
            await ctx.send(
                embed=disnake.Embed(title="🚀 Meeting Details Revealed", description=links)
            )
        else:
            channel_message = next(
                (message for message in messages if message.channel.id == ctx.channel.id),
                None,
            )
            if channel_message:
                await channel_message.reply(
                    f"🚀 Meeting details revealed: {channel_message.jump_url}"
                )
            else:
                await ctx.channel.send("🚀 Meeting details revealed.")

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

    @zzzzoom_group.command(
        name="setup",
        help="Set up a Zoom before revealing its details to other users. Useful for meetings that have breakout rooms.",
    )
    @check(is_allowed_zoom_access)
    async def zzzzoom_setup(
        self, ctx: Context, meeting_id: Optional[Union[int, str]] = None
    ):
        await self.zoom_setup_impl(ctx, meeting_id=meeting_id, with_zzzzoom=True)

    @zoom_command.error
    @zzzzoom_group.error
    @zzzzoom_setup.error
    @zoom_group.error
    @zoom_setup.error
    async def zoom_error(self, ctx, error):
        if isinstance(error, ZoomCreateError):
            logger.error("could not create zoom due to unexpected error", exc_info=error)
            await ctx.send(error)

    async def zoom_group_impl(
        self, ctx: Context, *, meeting_id: Optional[Union[int, str]], with_zzzzoom: bool
    ):
        await ctx.channel.trigger_typing()

        async def send_channel_message(mid: int):
            return await ctx.reply(embed=await make_zoom_embed(mid))

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

    async def zoom_setup_impl(
        self, ctx: Context, meeting_id: Optional[Union[int, str]], with_zzzzoom: bool
    ):
        await ctx.channel.trigger_typing()

        async def send_channel_message(_):
            return await ctx.reply(
                embed=disnake.Embed(
                    color=disnake.Color.blue(),
                    title="✋ Stand By",
                    description="Zoom details will be posted here when the meeting is ready to start.",
                )
            )

        meeting_id, _ = await zoom_impl(
            bot=self.bot,
            zoom_user=settings.ZOOM_USERS[ctx.author.id],
            channel_id=ctx.channel.id,
            meeting_id=meeting_id,
            send_channel_message=send_channel_message,
            set_up=False,
            with_zzzzoom=with_zzzzoom,
        )

        zoom_messages = tuple(await store.get_zoom_messages(meeting_id=meeting_id))
        # DM zoom link and instructions once
        if len(zoom_messages) <= 1:
            command_name = "zzzzoom" if with_zzzzoom else "zoom"
            await ctx.author.send(
                content="🔨 Set up your meeting below",
                embed=await make_zoom_embed(meeting_id, include_instructions=False),
            )
            await ctx.author.send(
                "To post in another channel, send the following command in that channel:\n"
                f"```{COMMAND_PREFIX}{command_name} setup {meeting_id}```\n"
                "When you're ready for people to join, reply with:\n"
                f"```{COMMAND_PREFIX}zoom start {meeting_id}```"
            )

    # End deprecated prefix commands

    @command(name="meet", aliases=("jitsi",), help="Start a Jitsi Meet meeting")
    async def meet_command(self, ctx: Context, *, name: Optional[str]):
        meeting = meetings.create_jitsi_meet(name, secret=settings.SECRET_KEY)
        logger.info("sending jitsi meet info")
        message = await ctx.send(embed=make_jitsi_embed(meeting))

        await add_stop_sign(message)

    @command(name="speakeasy", help="Start a Speakeasy (https://speakeasy.co/) event")
    async def speakeasy_command(self, ctx: Context, *, name: Optional[str]):
        join_url = meetings.create_speakeasy(name, secret=settings.SECRET_KEY)
        content = f"️🍻 **Speakeasy**\nJoin URL: <{join_url}>"
        if name:
            content = f"{content}\n**Name**: {name}"
        content = f"{content}\n🚀 This event is happening now. Make a friend!"
        logger.info("sending speakeasy info")
        message = await ctx.send(content=content)
        await add_stop_sign(message)

    @command(name="w2g", aliases=("wtg", "watch2gether"), help=WATCH2GETHER_HELP)
    async def watch2gether_command(self, ctx: Context, video_url: Optional[str] = None):
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

    async def edit_meeting_moved(self, message: disnake.Message) -> None:
        await message.edit(
            content=f"{REPOST_EMOJI} *Meeting details moved below.*",
            embed=None,
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
                    channel = self.bot.get_channel(message.channel.id)
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
            new_message = await send_method(
                content="👐 **This meeting is still going**. Come on in!",
                embed=await make_zoom_embed(zoom_message["meeting_id"]),
                mention_author=False,
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
                r"zoom\.us|Stand By|Could not create Zoom": close_zoom_message,
                r"meet\.jit\.si": MEET_CLOSED_MESSAGE,
                r"Speakeasy": SPEAKEASY_CLOSED_MESSAGE,
                r"w2g\.tv|Could not create watch2gether": WATCH2GETHER_CLOSED_MESSAGE,
            },
        )


def setup(bot: Bot) -> None:
    bot.add_cog(Meetings(bot))
