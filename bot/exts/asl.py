import logging
from urllib.parse import quote_plus

import discord
from discord.ext.commands import Cog, Bot, Context, command, errors

import handshapes
from bot import settings
from bot.utils import get_spoiler_text, did_you_mean

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX

SIGN_TEMPLATE = """[🤲 **Handspeak** - Search results]({handspeak})
[🧬 **Lifeprint** - Search results]({lifeprint})
[🤝 **SigningSavvy** - Sign for {word_uppercased}]({signingsavvy})
[🌐 **Spread The Sign** - {word_uppercased}]({spread_the_sign})
[📹 **YouGlish** - ASL videos with {word_uppercased}]({youglish})
Share: {howsign}
"""

SIGN_SPOILER_TEMPLATE = """[🤲 **Handspeak** - Search results]({handspeak})
[🧬 **Lifeprint** - Search results]({lifeprint})
[🤝 **SigningSavvy** - Sign for ||{word_uppercased}||]({signingsavvy})
[🌐 **Spread The Sign** - ||{word_uppercased}||]({spread_the_sign})
[📹 **YouGlish** - ASL videos with ||{word_uppercased}||]({youglish})
Share: ||{howsign}||
"""

SIGN_HELP = """Look up a word or phrase

If the word or phrase is sent in spoiler text, i.e. enclosed in `||`, the word will also be blacked out in the reply.
To search multiple words/phrases, separate the values with a comma.

Examples:
{COMMAND_PREFIX}sign tiger
{COMMAND_PREFIX}sign ||tiger||
{COMMAND_PREFIX}sign what's up
{COMMAND_PREFIX}sign church, chocolate, computer
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def word_display(word: str, *, template: str = SIGN_TEMPLATE, max_length: int = 100):
    if len(word) > max_length:
        raise errors.BadArgument("⚠️ Input too long. Try a shorter query.")
    quoted_word = quote_plus(word).lower()
    return template.format(
        word_uppercased=word.upper(),
        howsign=f"https://howsign.app/?s={quoted_word}",
        lifeprint=f"https://www.google.com/search?&q=site%3Alifeprint.com+{quoted_word}",
        handspeak=f"https://www.google.com/search?&q=site%3Ahandspeak.com+{quoted_word}",
        signingsavvy=f"https://www.signingsavvy.com/search/{quoted_word}",
        spread_the_sign=f"https://www.spreadthesign.com/en.us/search/?q={quoted_word}",
        youglish=f"https://youglish.com/pronounce/{quoted_word}/signlanguage/asl",
    )


def sign_impl(word: str):
    logger.info(f"sending links for: '{word}'")
    spoiler = get_spoiler_text(word)
    word = spoiler if spoiler else word
    has_multiple = "," in word
    template = SIGN_SPOILER_TEMPLATE if spoiler else SIGN_TEMPLATE
    if has_multiple:
        words = word.split(",")
        embed = discord.Embed()
        for word in words:
            word = word.strip()
            title = f"||{word.upper()}||" if spoiler else word.upper()
            embed.add_field(name=title, value=word_display(word, template=template))
    else:
        title = f"||{word.upper()}||" if spoiler else word.upper()
        embed = discord.Embed(
            title=title,
            description=word_display(word, template=template),
        )

    return {"embed": embed}


HANDSHAPE_HELP = """Show a random or specific handshape

Examples:
{COMMAND_PREFIX}handshape
{COMMAND_PREFIX}handshape claw5

Enter {COMMAND_PREFIX}handshapes to show a list of handshapes.
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def handshape_impl(name: str):
    logger.info(f"handshape: '{name}'")
    try:
        if name == "random":
            handshape = handshapes.get_random_handshape()
        else:
            handshape = handshapes.get_handshape(name)
    except handshapes.HandshapeNotFoundError:
        logger.info(f"handshape '{name}' not found")
        suggestion = did_you_mean(name, tuple(handshapes.HANDSHAPES.keys()))
        if suggestion:
            return {
                "content": f'"{name}" not found. Did you mean "{suggestion}"? Enter `{COMMAND_PREFIX}handshapes` to see a list of handshapes.'
            }
        else:
            return {
                "content": f'"{name}" not found. Enter `{COMMAND_PREFIX}handshapes` to see a list of handshapes.'
            }

    filename = f"{handshape.name}.png"
    file_ = discord.File(handshape.path, filename=filename)
    embed = discord.Embed(title=handshape.name)
    embed.set_image(url=f"attachment://{filename}")
    return {
        "file": file_,
        "embed": embed,
    }


HANDSHAPES_TEMPLATE = """{handshapes}

Enter `{COMMAND_PREFIX}handshape` to display a random handshape or `{COMMAND_PREFIX}handshape [name]` to display a specific handshape.
"""

HANDSHAPES_HELP = """List handshapes

Enter {COMMAND_PREFIX}handshape to display a random handshape or {COMMAND_PREFIX}handshape [name] to display a specific handshape.
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def handshapes_impl():
    return {
        "content": HANDSHAPES_TEMPLATE.format(
            handshapes=", ".join(handshapes.HANDSHAPES.keys()),
            COMMAND_PREFIX=COMMAND_PREFIX,
        )
    }


class ASL(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @command(name="sign", aliases=("howsign", COMMAND_PREFIX), help=SIGN_HELP)
    async def sign_command(self, ctx: Context, *, word: str):
        await ctx.send(**sign_impl(word))

    @sign_command.error
    async def sign_error(self, ctx: Context, error: Exception):
        # Ignore "??"
        if isinstance(error, errors.MissingRequiredArgument):
            if ctx.invoked_with == COMMAND_PREFIX:
                logger.info(
                    f"no argument passed to {COMMAND_PREFIX}{ctx.invoked_with}. ignoring..."
                )
            else:
                await ctx.send(
                    f"⚠️ Enter a word or phrase to search for after `{COMMAND_PREFIX}{ctx.invoked_with}`."
                )

    @command(name="handshape", aliases=("shape",), help=HANDSHAPE_HELP)
    async def handshape_command(self, ctx: Context, name="random"):
        await ctx.send(**handshape_impl(name))

    @command(name="handshapes", aliases=("shapes",), help=HANDSHAPES_HELP)
    async def handshapes_command(self, ctx: Context):
        logger.info("sending handshapes list")
        await ctx.send(**handshapes_impl())


def setup(bot: Bot) -> None:
    bot.add_cog(ASL(bot))
