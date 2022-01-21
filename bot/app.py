import asyncio
import logging

import aiohttp_cors
from aiohttp import web
from ariadne import graphql
from ariadne.constants import PLAYGROUND_HTML

from . import settings
from .bot import bot
from .database import store
from .graphql.schema import schema
from .utils.extensions import walk_extensions

logger = logging.getLogger(__name__)

# Assign app to bot so that extensions can add routes
bot.app = app = web.Application()  # type: ignore

app.cors = cors = aiohttp_cors.setup(
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


def graphql_playground(_):
    return web.Response(text=PLAYGROUND_HTML, status=200, content_type="text/html")


async def graphql_server(request):
    data = await request.json()

    success, result = await graphql(
        schema, data, context_value=request, debug=settings.DEBUG
    )

    status = 200 if success else 400
    return web.json_response(result, status=status)


app.add_routes([web.get("/ping", ping)])
resource = bot.app.router.add_resource("/graphql")  # type: ignore
cors.add(resource.add_route("POST", graphql_server))


async def start_bot():
    try:
        await bot.start(settings.DISCORD_TOKEN)
    finally:
        await bot.close()


async def on_startup(app):
    for ext in walk_extensions():
        bot.load_extension(ext)
    await store.connect()
    app["bot_task"] = asyncio.create_task(start_bot())
    app["bot"] = bot


async def on_shutdown(app):
    app["bot_task"].cancel()
    await app["bot_task"]
    await store.disconnect()


app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)
