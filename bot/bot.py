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


@bot.event
async def on_ready():
    await set_default_presence()


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
        name=f"{COMMAND_PREFIX}sign | {COMMAND_PREFIX}{COMMAND_PREFIX}",
        type=disnake.ActivityType.watching,
    )
    await bot.change_presence(activity=activity)
