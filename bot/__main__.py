import logging

from aiohttp import web

from . import __version__, settings
from .app import app, bot

log_format = "%(asctime)s - %(name)s %(levelname)s: %(message)s"
logging.getLogger("disnake").setLevel(logging.WARNING)
logging.basicConfig(
    format=log_format,
    level=settings.LOG_LEVEL,
)
logger = logging.getLogger(__name__)

logger.info(f"starting bot version {__version__}")
web.run_app(app, loop=bot.loop, port=settings.PORT)
