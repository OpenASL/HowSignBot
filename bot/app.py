import asyncio
import logging

import aiohttp_cors
from aiohttp import web

from . import settings
from .bot import bot
from .database import store
from .utils.extensions import walk_extensions

logger = logging.getLogger(__name__)

# Assign app to bot so that extensions can add routes
bot.app = app = web.Application()

app.cors = aiohttp_cors.setup(
    app,
    defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=False,
            expose_headers="*",
            allow_headers="*",
        )
    },
)


async def ping(_):
    return web.Response(body="", status=200)


app.add_routes([web.get("/ping", ping)])


async def start_bot():
    try:
        await bot.start(settings.DISCORD_TOKEN)
    finally:
        await bot.close()


async def on_startup(app):
    for ext in walk_extensions():
        bot.load_extension(ext)
    app["bot_task"] = asyncio.create_task(start_bot())
    app["bot"] = bot
    await store.connect()


async def on_shutdown(app):
    app["bot_task"].cancel()
    await app["bot_task"]
    await store.disconnect()


app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)
