import logging
from typing import List, Optional, cast
from contextlib import suppress

import discord
from discord.ext.commands import Bot, Context, Cog, errors, group, check, command

import meetings
from bot import settings
from bot.database import store
from bot.utils.reactions import (
    handle_close_reaction,
    add_stop_sign,
    STOP_SIGN,
    get_reaction_message,
    should_handle_reaction,
)
from ._zoom import (
    make_zoom_embed,
    add_repost_after_delay,
    zoom_impl,
    is_allowed_zoom_access,
    ZOOM_CLOSED_MESSAGE,
    REPOST_EMOJI,
    ZoomCreateError,
)

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX

MEET_CLOSED_MESSAGE = "✨ _Jitsi Meet ended_"
SPEAKEASY_CLOSED_MESSAGE = "✨ _Speakeasy event ended_"
WATCH2GETHER_HELP = """Start a watch2gether session

You can optionally pass a URL to use for the first video.

Examples:
{COMMAND_PREFIX}w2g
{COMMAND_PREFIX}w2g https://www.youtube.com/watch?v=DaMjr4AfYA0
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
    return discord.Embed(
        title=title,
        description=content,
        color=discord.Color.blue(),
    )


def make_watch2gether_embed(url: str, video_url: Optional[str]) -> discord.Embed:
    description = "🚀 Watch videos together!"
    if video_url:
        description += f"\nQueued video: <{video_url}>"
    description += "\n*When finished, click 🛑 to remove this message.*"
    return discord.Embed(title=url, description=description, color=discord.Color.gold())


class Meetings(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @group(name="zoom", invoke_without_command=True)
    @check(is_allowed_zoom_access)
    async def zoom_group(self, ctx: Context, meeting_id: Optional[int] = None):
        """AUTHORIZED USERS ONLY: Start a Zoom meeting"""
        await ctx.channel.trigger_typing()

        async def send_channel_message(mid: int):
            return await ctx.send(embed=await make_zoom_embed(mid))

        _, message = await zoom_impl(
            ctx,
            meeting_id=meeting_id,
            send_channel_message=send_channel_message,
            set_up=True,
        )

    @zoom_group.command(
        name="setup",
        help="Set up a Zoom before revealing its details to other users. Useful for meetings that have breakout rooms.",
    )
    @check(is_allowed_zoom_access)
    async def zoom_setup(self, ctx: Context, meeting_id: Optional[int] = None):
        await ctx.channel.trigger_typing()

        async def send_channel_message(_):
            return await ctx.channel.send(
                embed=discord.Embed(
                    color=discord.Color.blue(),
                    title="✋ Stand By",
                    description="Zoom details will be posted here when the meeting is ready to start.",
                )
            )

        meeting_id, _ = await zoom_impl(
            ctx,
            meeting_id=meeting_id,
            send_channel_message=send_channel_message,
            set_up=False,
        )

        zoom_messages = tuple(await store.get_zoom_messages(meeting_id=meeting_id))
        # DM zoom link and instructions once
        if len(zoom_messages) <= 1:
            await ctx.author.send(
                content="🔨 Set up your meeting below",
                embed=await make_zoom_embed(meeting_id, include_instructions=False),
            )
            await ctx.author.send(
                "To post in another channel, send the following command in that channel:\n"
                f"```{COMMAND_PREFIX}zoom setup {meeting_id}```\n"
                "When you're ready for people to join, reply with:\n"
                f"```{COMMAND_PREFIX}zoom start {meeting_id}```"
            )

    @zoom_group.error
    @zoom_setup.error
    async def zoom_error(self, ctx, error):
        if isinstance(error, ZoomCreateError):
            logger.error("could not create zoom due to unexpected error", exc_info=error)
            await ctx.send(error)

    @zoom_group.command(
        name="start",
        help="Reveal meeting details for a meeting started with the setup command.",
    )
    @check(is_allowed_zoom_access)
    async def zoom_start(self, ctx: Context, meeting_id: Optional[int] = None):
        await ctx.channel.trigger_typing()
        if meeting_id:
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
        messages: List[discord.Message] = []
        for message_info in zoom_messages:
            channel_id = message_info["channel_id"]
            message_id = message_info["message_id"]
            channel = self.bot.get_channel(channel_id)
            message: discord.Message = await channel.fetch_message(message_id)
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
                embed=discord.Embed(title="🚀 Meeting Details Revealed", description=links)
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

    @zoom_group.command(
        name="stop",
        help="Remove meeting details for a meeting.",
    )
    @check(is_allowed_zoom_access)
    async def zoom_stop(self, ctx: Context, meeting_id: int):
        await ctx.channel.trigger_typing()
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
            message: discord.Message = await channel.fetch_message(message_id)
            messages.append(message)
            logger.info(
                f"revealing meeting details for meeting {meeting_id} in channel {channel_id}, message {message_id}"
            )
            await message.edit(content=ZOOM_CLOSED_MESSAGE, embed=None)
        await store.end_zoom_meeting(meeting_id=meeting_id)
        if ctx.guild is None:
            links = "\n".join(
                f"[{message.guild} - #{message.channel}]({message.jump_url})"
                for message in messages
            )
            await ctx.send(
                embed=discord.Embed(title="🛑 Meeting Ended", description=links)
            )
        else:
            await ctx.channel.send("🛑 Meeting details removed.")

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

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if should_handle_reaction(self.bot, payload, {"↩️"}):
            message = await get_reaction_message(self.bot, payload)
            if not message:
                return
            zoom_message = await store.get_zoom_message(message.id)
            if not zoom_message:
                return
            await message.edit(content="✨ *Meeting details moved below.*", embed=None)

            new_message = await message.reply(
                content="👐 **This meeting is still going**. Come on in!",
                embed=await make_zoom_embed(zoom_message["meeting_id"]),
            )
            add_repost_after_delay(self.bot, new_message)

            async with store.transaction():
                await store.create_zoom_message(
                    message_id=new_message.id,
                    channel_id=new_message.channel.id,
                    meeting_id=zoom_message["meeting_id"],
                )
                await store.remove_zoom_message(message_id=zoom_message["message_id"])

        async def close_zoom_message(msg: discord.Message):
            await store.remove_zoom_message(message_id=msg.id)
            with suppress(Exception):
                await msg.clear_reaction(REPOST_EMOJI)
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
