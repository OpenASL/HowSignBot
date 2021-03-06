import logging
import discord
from discord.ext import commands

from . import settings

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX


intents = discord.Intents.default()
intents.typing = False
intents.presences = False
intents.bans = False
intents.integrations = False
intents.webhooks = False
intents.invites = False
bot = commands.Bot(
    command_prefix=COMMAND_PREFIX,
    case_insensitive=True,
    owner_id=settings.OWNER_ID,
    intents=intents,
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


async def set_default_presence():
    activity = discord.Activity(
        name=f"{COMMAND_PREFIX}sign | {COMMAND_PREFIX}{COMMAND_PREFIX}",
        type=discord.ActivityType.watching,
    )
    await bot.change_presence(activity=activity)
