import asyncio
import itertools
import logging

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

from . import settings

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX


intents = disnake.Intents.default()
intents.typing = False
intents.presences = False
intents.bans = False
intents.integrations = False
intents.webhooks = False
intents.invites = False
intents.members = True
intents.messages = True
bot = commands.Bot(
    command_prefix=COMMAND_PREFIX,
    case_insensitive=True,
    owner_id=settings.OWNER_ID,
    intents=intents,
    sync_commands_debug=settings.DEBUG,
    reload=settings.DEBUG,
    test_guilds=settings.TEST_GUILDS or None,
)

PRESENCE_COMMANDS = (
    "/sign",
    "/handshape",
    "/catchphrase | /codenames",
    "/schedule new",
    "/watch2gether",
    "/sentence | /idiom",
    "/feedback",
)
CHANGE_PRESENCE_EVERY = 120  # seconds


async def cycle_presence():
    for command in itertools.cycle(PRESENCE_COMMANDS):
        activity = disnake.Activity(
            name=command,
            type=disnake.ActivityType.watching,
        )
        logger.debug(f"changing presence to show command: {command}")
        await bot.change_presence(activity=activity)
        await asyncio.sleep(CHANGE_PRESENCE_EVERY)


@bot.event
async def on_ready():
    bot.loop.create_task(cycle_presence())


@bot.event
async def on_command_error(ctx, error):
    if isinstance(
        error,
        (commands.errors.CheckFailure, commands.errors.BadArgument),
    ):
        await ctx.send(error)
    else:
        logger.error(f"unhandled exception from command: {ctx.command}", exc_info=error)


@bot.event
async def on_slash_command_error(inter: ApplicationCommandInteraction, error: Exception):
    if isinstance(
        error,
        (commands.errors.CheckFailure, commands.errors.BadArgument),
    ):
        await inter.send(error)
    else:
        logger.error(
            f"unhandled exception from command: {inter.application_command.name!r}",
            exc_info=error,
        )


async def set_default_presence():
    activity = disnake.Activity(
        name="/sign",
        type=disnake.ActivityType.watching,
    )
    await bot.change_presence(activity=activity)
