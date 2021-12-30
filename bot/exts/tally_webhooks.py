from __future__ import annotations

import asyncio
import hashlib
import logging
from contextlib import suppress
from typing import Any
from typing import NamedTuple
from typing import TypedDict

import disnake
from aiohttp import web
from disnake.ext.commands import Bot

from bot import settings
from bot.database import store
from bot.utils.gsheets import get_gsheet_client
from bot.utils.ui import LinkView

logger = logging.getLogger(__name__)

WORKSHEET_NAME = "feedback-submissions"


async def add_submission_to_gsheet(
    *, worksheet, bot: Bot, submission: Submission, discord_user_id: int | None
):
    join_month, role_names = "", ""
    if discord_user_id:
        aslpp_member = await store.get_aslpp_member(discord_user_id)
        if aslpp_member:
            join_month = aslpp_member["joined_at"].strftime("%Y-%m")
        guild: disnake.Guild = bot.get_guild(settings.ASLPP_GUILD_ID)
        member = guild.get_member(discord_user_id)
        if member:
            # Skip the @everyone role
            roles = member.roles[1:]
            role_names = "|".join([role.name for role in roles])
    row = (join_month, role_names) + submission
    worksheet.append_row(row)


def hash_int(integer: int) -> str:
    hash_object = hashlib.sha1(str(integer).encode("utf8"))
    return hash_object.hexdigest()


USER_ID_KEY = "question_wbj5B2_e34181f0-00e1-47ae-a3a8-063f16f5821d"
FIELD_KEYS_TO_SUBMISSION_FIELDS = {
    "question_nWEOGP": "practice_session_participation",
    "question_wa5QbE": "proficiency_improvement",
    "question_nP1R1x": "ways_improved",
    "question_mRMWKP": "does_host",
    "question_woe96M": "wants_to_host",
    "question_nG9evz": "staff_can_follow_up",
    "question_mO4QDA": "discord_username",
    "question_m6j8bO": "practice_suggestion",
    "question_w7LRB9": "server_suggestion",
    "question_3y2PKp": "source",
}


class Submission(NamedTuple):
    # NOTE: The order of fields must match the left-to-right order in the Google Sheet
    created_at: str
    hashed_user_id: str
    # NOTE: integer values get stringified
    practice_session_participation: str
    proficiency_improvement: str
    ways_improved: str
    does_host: str
    wants_to_host: str
    staff_can_follow_up: str
    discord_username: str
    practice_suggestion: str
    server_suggestion: str
    source: str


class Option(TypedDict):
    id: str
    text: str


class Field(TypedDict, total=False):
    key: str
    label: str
    type: str
    value: Any
    options: list[Option]


# NOTE: Not all field types are supported here--just the ones that are actually used
def get_field_value(field: Field) -> str:
    value = field["value"]
    if value is None:
        return ""
    if field["type"] == "MULTIPLE_CHOICE":
        options = field["options"]
        option_map = {option["id"]: option["text"] for option in options}
        return option_map[value] or ""
    else:
        return str(value) if value else ""


async def handle_tally_webhook(bot: Bot, data: dict):
    submission, discord_user_id = make_submission(data)
    if not submission:
        return
    logger.info(f"adding feedback submission to gsheet: {submission}")
    client = get_gsheet_client()
    sheet = client.open_by_key(settings.ASLPP_SHEET_KEY)
    worksheet = sheet.worksheet(WORKSHEET_NAME)
    await add_submission_to_gsheet(
        worksheet=worksheet,
        bot=bot,
        submission=submission,
        discord_user_id=discord_user_id,
    )

    url = f"https://docs.google.com/spreadsheets/d/{settings.ASLPP_SHEET_KEY}/edit#gid={worksheet.id}"
    await bot.get_channel(settings.ASLPP_BOT_CHANNEL_ID).send(
        "🙌 A member submitted the survey!",
        view=LinkView("Survey Results", url=url),
    )


def make_submission(
    data: dict[str, Any],
) -> tuple[Submission | None, int | None]:
    if not data.get("eventType") == "FORM_RESPONSE":
        return None, None
    try:
        fields: list[Field] = data["data"]["fields"]
        created_at = data["data"]["createdAt"]
    except KeyError:
        return None, None

    discord_user_id = None
    submission_fields: dict[str, str] = {}
    for field in fields:
        key = field["key"]
        if key == USER_ID_KEY:
            with suppress(ValueError):
                discord_user_id = int(field["value"])
        elif key in FIELD_KEYS_TO_SUBMISSION_FIELDS:
            submission_field_key = FIELD_KEYS_TO_SUBMISSION_FIELDS[key]
            submission_fields[submission_field_key] = get_field_value(field)

    return (
        Submission(
            created_at=created_at,
            hashed_user_id=hash_int(discord_user_id) if discord_user_id else "",
            **submission_fields,
        ),
        discord_user_id,
    )


def setup(bot: Bot) -> None:
    async def tally(request):
        data = await request.json()
        # Run the handler logic asynchronously to respond quickly
        asyncio.create_task(handle_tally_webhook(bot, data))
        return web.Response(body="", status=200)

    bot.app.add_routes([web.post("/tally", tally)])
