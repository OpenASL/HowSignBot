from __future__ import annotations

import asyncio
import hashlib
import logging
from contextlib import suppress
from typing import Any, NamedTuple, TypedDict

import disnake
from aiohttp import web
from disnake import GuildCommandInteraction
from disnake.ext import commands
from disnake.ext.commands import (
    Bot,
    Context,
    group,
    guild_permissions,
    is_owner,
    slash_command,
)

from bot import settings
from bot.database import store
from bot.utils.datetimes import utcnow
from bot.utils.gsheets import get_gsheet_client
from bot.utils.ui import LinkView

logger = logging.getLogger(__name__)

WORKSHEET_NAME = "feedback-submissions"

SUCCESS_MESSAGE = """🙌 Thank you for taking the survey. You're a champ!
I've applied a very special vanity role to your member profile."""


async def add_submission_and_apply_role(
    *, worksheet, bot: Bot, submission: Submission, discord_user_id: int | None
):
    join_month, role_names = "", ""
    if discord_user_id:
        aslpp_member = await store.get_aslpp_member(discord_user_id)
        if aslpp_member:
            join_month = aslpp_member["joined_at"].strftime("%Y-%m")
        guild = bot.get_guild(settings.ASLPP_GUILD_ID)
        assert guild is not None
        member = guild.get_member(discord_user_id)
        if member:
            # Skip the @everyone role
            roles = member.roles[1:]
            role_names = "|".join([role.name for role in roles])
            if settings.ASLPP_SURVEY_VANITY_ROLE_ID:
                try:
                    logger.debug("applying survey vanity role")
                    await member.add_roles(
                        disnake.Object(id=settings.ASLPP_SURVEY_VANITY_ROLE_ID),
                        reason="Completed survey",
                    )
                except Exception:
                    logger.exception("failed to add vanity role for survey submission")
                else:
                    with suppress(disnake.errors.Forbidden):
                        await member.send(SUCCESS_MESSAGE)
    row = (join_month, role_names) + submission
    worksheet.append_row(row)


def hash_int(integer: int) -> str:
    hash_object = hashlib.sha1(str(integer).encode("utf8"))
    return hash_object.hexdigest()


USER_ID_KEY = "question_wbj5B2_e34181f0-00e1-47ae-a3a8-063f16f5821d"
FIELD_KEYS_TO_SUBMISSION_FIELDS = {
    "question_nWEOGP": "meeting_participation",
    "question_w4Jalr": "meeting_absence_reasons",
    "question_3j6e8Q": "meeting_absence_reasons_other",
    "question_mRMWKP": "does_host",
    "question_woe96M": "wants_to_host",
    "question_nG9evz": "staff_can_follow_up",
    "question_mO4QDA": "discord_username",
    "question_m6j8bO": "meeting_suggestion",
    "question_wa5QbE": "proficiency_improvement",
    "question_nP1R1x": "ways_improved",
    "question_w2aj9e": "server_like",
    "question_w7LRB9": "server_suggestion",
    "question_3xMV8d": "other_feedback",
    "question_3y2PKp": "source",
}


class Submission(NamedTuple):
    # NOTE: The order of fields must match the left-to-right order in the Google Sheet
    created_at: str
    hashed_user_id: str
    # NOTE: integer values get stringified
    meeting_participation: str
    meeting_absence_reasons: str
    meeting_absence_reasons_other: str
    does_host: str
    wants_to_host: str
    staff_can_follow_up: str
    discord_username: str
    meeting_suggestion: str
    proficiency_improvement: str
    ways_improved: str
    server_like: str
    server_suggestion: str
    other_feedback: str
    source: str


class Option(TypedDict):
    id: str
    text: str


class Field(TypedDict):
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
    elif field["type"] == "CHECKBOXES":
        options = field["options"]
        option_map = {option["id"]: option["text"] for option in options}
        return "|".join(option_map[v] for v in value)
    else:
        return str(value) if value else ""


def get_worksheet():
    client = get_gsheet_client()
    sheet = client.open_by_key(settings.ASLPP_SHEET_KEY)
    return sheet.worksheet(WORKSHEET_NAME)


async def handle_tally_webhook(bot: Bot, data: dict):
    submission, discord_user_id = make_submission(data)
    if not submission:
        return
    logger.info("adding feedback submission to gsheet")
    logger.debug(f"submission: {submission}")
    worksheet = get_worksheet()
    await add_submission_and_apply_role(
        worksheet=worksheet,
        bot=bot,
        submission=submission,
        discord_user_id=discord_user_id,
    )

    url = f"https://docs.google.com/spreadsheets/d/{settings.ASLPP_SHEET_KEY}/edit#gid={worksheet.id}"
    channel = bot.get_channel(settings.ASLPP_BOT_CHANNEL_ID)
    assert channel is not None
    await channel.send(  # type: ignore
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
            with suppress(ValueError, TypeError):
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


class Survey(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @guild_permissions(
        settings.ASLPP_GUILD_ID, roles={settings.ASLPP_ACKNOWLEDGED_RULES_ROLE_ID: True}
    )
    @slash_command(
        name="survey", guild_ids=(settings.ASLPP_GUILD_ID,), default_permission=False
    )
    async def survey_command(self, inter: GuildCommandInteraction):
        """Get a link for the ASL Practice Partners feedback survey"""
        assert inter.user is not None
        url = f"https://tally.so/r/{settings.ASLPP_SURVEY_ID}?uid={inter.user.id}"
        await inter.send(
            "🙌 We love feedback! Here's the survey link. It'll take less than 5 minutes to complete.",
            view=LinkView(label="Survey Link", url=url),
            ephemeral=True,
        )

    @group(name="survey", hidden=True)
    async def survey_group(self, ctx: Context):
        pass

    @survey_group.command(name="test", hidden=True)
    @is_owner()
    async def test_command(self, ctx: Context):
        await ctx.channel.trigger_typing()
        worksheet = get_worksheet()
        submission = Submission(
            created_at=utcnow().isoformat(),
            hashed_user_id=hash_int(ctx.author.id),
            meeting_participation="5",
            meeting_absence_reasons="The meetings are at an inconvenient time|Other -  please specify",
            meeting_absence_reasons_other="TEST",
            does_host="No",
            wants_to_host="Yes",
            staff_can_follow_up="Yes",
            discord_username="TEST",
            meeting_suggestion="TEST",
            proficiency_improvement="4",
            ways_improved="TEST",
            server_like="TEST",
            server_suggestion="TEST",
            other_feedback="TEST",
            source="TEST",
        )
        await add_submission_and_apply_role(
            worksheet=worksheet,
            bot=self.bot,
            submission=submission,
            discord_user_id=ctx.author.id,
        )
        await ctx.reply("✅ Test submission sent.")


def setup(bot: Bot) -> None:
    async def tally(request):
        data = await request.json()
        # Run the handler logic asynchronously to respond quickly
        asyncio.create_task(handle_tally_webhook(bot, data))
        return web.Response(body="", status=200)

    bot.app.add_routes([web.post("/tally", tally)])  # type: ignore
    bot.add_cog(Survey(bot))
