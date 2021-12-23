import asyncio
import datetime as dt
import logging
from typing import cast

import dateparser
import disnake
from aiohttp import web
from disnake.ext.commands import Bot

from ._zoom import make_zoom_embed
from ._zoom import REPOST_EMOJI
from bot import settings
from bot.database import store
from bot.utils.reactions import maybe_clear_reaction

logger = logging.getLogger(__name__)

SUPPORTED_EVENTS = {
    "meeting.participant_joined",
    "meeting.participant_left",
    "meeting.ended",
}


async def handle_zoom_event(bot: Bot, data: dict):
    event = data["event"]
    if event not in SUPPORTED_EVENTS:
        return
    # meeting ID can be None for breakout room events
    if data["payload"]["object"]["id"] is None:
        return

    meeting_id = int(data["payload"]["object"]["id"])
    zoom_meeting = await store.get_zoom_meeting(meeting_id=meeting_id)
    if not zoom_meeting:
        return
    messages = tuple(await store.get_zoom_messages(meeting_id=meeting_id))
    logging.info(f"handling zoom event {event} for meeting {meeting_id}")

    # Update cached host id
    # XXX: As of this 2021-02-20, Zoom does not update the host_id in webhooks
    #  even after the host has changed, so this won't actually have any effect on
    #  the participant indicators, but it doesn't hurt to do this.
    if "host_id" in data["payload"]["object"]:
        await store.set_zoom_meeting_host_id(
            meeting_id, host_id=data["payload"]["object"]["host_id"]
        )

    edit_kwargs = None
    banned_user_joined = False
    if event == "meeting.ended":
        logger.info(f"automatically ending zoom meeting {meeting_id}")
        await store.end_zoom_meeting(meeting_id=meeting_id)
        edit_kwargs = {"content": "✨ _Zoom meeting ended by host_", "embed": None}
    elif event == "meeting.participant_joined":
        participant_data = data["payload"]["object"]["participant"]
        # Use user_name as the identifier for participants because id isn't guaranteed to
        #   be present and user_id will differ for the same user if breakout rooms are used.
        participant_name = participant_data["user_name"]
        joined_at = cast(
            dt.datetime, dateparser.parse(participant_data["join_time"])
        ).astimezone(dt.timezone.utc)
        logger.info(f"adding new participant for meeting id {meeting_id}")
        email = participant_data["email"]
        await store.add_zoom_participant(
            meeting_id=meeting_id,
            name=participant_name,
            zoom_id=participant_data["id"],
            email=email,
            joined_at=joined_at,
        )
        embed = await make_zoom_embed(meeting_id=meeting_id)
        edit_kwargs = {"embed": embed}
        banned_user_joined = email in settings.ASLPP_ZOOM_WATCH_LIST
    elif event == "meeting.participant_left":
        # XXX Sleep to reduce the likelihood that particpants will be removed
        #   after leaving breakout rooms.
        await asyncio.sleep(1)
        participant_data = data["payload"]["object"]["participant"]
        participant_name = participant_data["user_name"]
        prev_participant = await store.get_zoom_participant(
            meeting_id=meeting_id, name=participant_name
        )
        if not prev_participant:
            return
        # XXX If the leave time is within a few seconds of the join time
        #  this likely a "leave" event for moving into a breakout room rather than
        #  a participant actually leaving. In this case, bail early.
        # .Unfortunately the payload doesn't give us a better way to distinbuish
        #  "leaving breakout room" vs "leaving meeting".
        joined_at = prev_participant["joined_at"]
        left_at = cast(
            dt.datetime, dateparser.parse(participant_data["leave_time"])
        ).astimezone(dt.timezone.utc)
        if abs((left_at - joined_at).seconds) < 2:
            logger.debug(
                f"left_at and joined_at within 2 seconds (likely breakout room event). skipping {event} for meeting id {meeting_id}"
            )
            return
        logger.info(f"removing participant for meeting id {meeting_id}")
        await store.remove_zoom_participant(meeting_id=meeting_id, name=participant_name)
        embed = await make_zoom_embed(meeting_id=meeting_id)
        edit_kwargs = {"embed": embed}

    disnake_messages = []
    if zoom_meeting["setup_at"]:
        for message in messages:
            channel_id = message["channel_id"]
            message_id = message["message_id"]
            channel = bot.get_channel(channel_id)
            if edit_kwargs:
                logger.info(f"editing zoom message {message_id} for event {event}")
                disnake_message: disnake.Message = await channel.fetch_message(message_id)
                disnake_messages.append(disnake_message)
                await disnake_message.edit(**edit_kwargs)
                if event == "meeting.ended":
                    await maybe_clear_reaction(disnake_message, REPOST_EMOJI)
    # If a banned user joins, notify @Mod in ASLPP
    if banned_user_joined:
        if disnake_messages:
            content = f"🚨 <@&{settings.ASLPP_MOD_ROLE_ID}> Banned user **{participant_name}** (email: **{email}**) entered a Zoom meeting: {disnake_messages[0].jump_url}"
        else:
            content = f"🚨 <@&{settings.ASLPP_MOD_ROLE_ID}> Banned user **{participant_name}** (email: **{email}**) entered a Zoom meeting."
        await bot.get_channel(settings.ASLPP_BOT_CHANNEL_ID).send(content=content)


def setup(bot: Bot) -> None:
    async def zoom(request):
        if request.headers["authorization"] != settings.ZOOM_HOOK_TOKEN:
            return web.Response(body="", status=403)
        data = await request.json()
        # Zoom expects responses within 3 seconds, so run the handler logic asynchronously
        #   https://marketplace.zoom.us/docs/api-reference/webhook-reference#notification-delivery
        asyncio.create_task(handle_zoom_event(bot, data))
        return web.Response(body="", status=200)

    bot.app.add_routes([web.post("/zoom", zoom)])
