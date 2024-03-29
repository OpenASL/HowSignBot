import logging
import re
from urllib.parse import quote_plus

import disnake
import handshapes
from disnake import ApplicationCommandInteraction
from disnake.ext.commands import Bot, Cog, Context, command, errors, slash_command

from bot import settings
from bot.utils import did_you_mean, get_close_matches, get_spoiler_text

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX

SIGN_TEMPLATE = """[🍃 **ASLCORE** - {word_uppercased}]({aslcore})
[📜 **ASL Signbank** - {word_uppercased}]({asl_signbank})
[🤲 **Handspeak** - Search results]({handspeak})
[🧬 **Lifeprint** - Search results]({lifeprint})
[🤝 **SigningSavvy** - Sign for {word_uppercased}]({signingsavvy})
[🌐 **Spread The Sign** - {word_uppercased}]({spread_the_sign})
[🔬 **STEM Dictionary** - {word_uppercased}]({stem_dictionary})
[📹 **YouGlish** - ASL videos with {word_uppercased}]({youglish})
Share: {howsign}
"""

SIGN_SPOILER_TEMPLATE = """[🍃 **ASLCORE** - ||{word_uppercased}||]({aslcore})
[📜 **ASL Signbank** - ||{word_uppercased}||]({asl_signbank})
[🤲 **Handspeak** - Search results]({handspeak})
[🧬 **Lifeprint** - Search results]({lifeprint})
[🤝 **SigningSavvy** - Sign for ||{word_uppercased}||]({signingsavvy})
[🌐 **Spread The Sign** - ||{word_uppercased}||]({spread_the_sign})
[🔬 **STEM Dictionary** - ||{word_uppercased}||]({stem_dictionary})
[📹 **YouGlish** - ASL videos with ||{word_uppercased}||]({youglish})
Share: ||{howsign}||
"""

SIGN_HELP = """Look up a word or phrase

If the word or phrase is sent in spoiler text, i.e. enclosed in `||`, the word will also be blacked out in the reply.
To search multiple words/phrases, separate the values with a comma.

Examples:
```
{COMMAND_PREFIX}sign tiger
{COMMAND_PREFIX}sign ||tiger||
{COMMAND_PREFIX}sign what's up
{COMMAND_PREFIX}sign church, chocolate, computer
```
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def word_display(word: str, *, template: str = SIGN_TEMPLATE, max_length: int = 100):
    if len(word) > max_length:
        raise errors.BadArgument("⚠️ Input too long. Try a shorter query.")
    quoted_word = quote_plus(word).lower()
    dasherized_word = re.sub(r"\s+", "-", word)
    quoted_dasherized_word = quote_plus(dasherized_word).lower()
    return template.format(
        word_uppercased=word.upper(),
        aslcore=f"https://aslcore.org/search/?query={quoted_word}&architecture=1&art=1&biology=1&computerscience=1&engineering=1&literature=1&organicchemistry=1&philosophy=1&physics=1&sustainability=1",
        asl_signbank=f"https://aslsignbank.haskins.yale.edu/signs/search/?translation={quoted_word}",
        howsign=f"https://howsign.app/?s={quoted_word}",
        lifeprint=f"https://www.google.com/search?&q=site%3Alifeprint.com+{quoted_word}",
        handspeak=f"https://www.google.com/search?&q=site%3Ahandspeak.com+{quoted_word}",
        signingsavvy=f"https://www.signingsavvy.com/search/{quoted_word}",
        spread_the_sign=f"https://www.spreadthesign.com/en.us/search/?q={quoted_word}",
        stem_dictionary=f"https://deaftec.org/stem-dictionary/dictionary_term/{quoted_dasherized_word}/",
        youglish=f"https://youglish.com/pronounce/{quoted_word}/signlanguage/us",
    )


def sign_impl(word: str):
    logger.info(f"sending links for: '{word}'")
    spoiler = get_spoiler_text(word)
    word = spoiler if spoiler else word
    has_multiple = "," in word
    template = SIGN_SPOILER_TEMPLATE if spoiler else SIGN_TEMPLATE
    if has_multiple:
        words = word.split(",")
        embed = disnake.Embed()
        for word in words:
            word = word.strip()
            title = f"||{word.upper()}||" if spoiler else word.upper()
            embed.add_field(name=title, value=word_display(word, template=template))
    else:
        title = f"||{word.upper()}||" if spoiler else word.upper()
        embed = disnake.Embed(
            title=title,
            description=word_display(word, template=template),
        )

    return {"embed": embed}


HANDSHAPE_HELP = """Show a random or specific handshape

Examples:
```
{COMMAND_PREFIX}handshape
{COMMAND_PREFIX}handshape claw5
```
Enter `{COMMAND_PREFIX}handshapes` to show a list of handshapes.
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
        suggestion = did_you_mean(name, handshapes.HANDSHAPE_NAMES)
        if suggestion:
            return {
                "content": f'"{name}" not found. Did you mean "{suggestion}"? Enter `{COMMAND_PREFIX}handshapes` to see a list of handshapes.'
            }
        else:
            return {
                "content": f'"{name}" not found. Enter `{COMMAND_PREFIX}handshapes` to see a list of handshapes.'
            }

    filename = f"{handshape.name}.png"
    file_ = disnake.File(handshape.path, filename=filename)
    embed = disnake.Embed(title=handshape.name)
    embed.set_image(url=f"attachment://{filename}")
    return {
        "file": file_,
        "embed": embed,
    }


HANDSHAPES_HELP = """List handshapes

Enter {COMMAND_PREFIX}handshape to display a random handshape or {COMMAND_PREFIX}handshape [name] to display a specific handshape.
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def handshapes_impl(prefix: str) -> dict[str, str]:
    return {"content": ", ".join(handshapes.HANDSHAPE_NAMES)}


class ASL(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @slash_command(name="sign")
    async def sign_command(self, inter: ApplicationCommandInteraction, term: str):
        """Look up a word or phrase in multiple ASL dictionaries

        Parameters
        ----------
        term: The word or phrase to look up
        """
        await inter.response.send_message(**sign_impl(term))

    @command(name="sign", aliases=("howsign", COMMAND_PREFIX), help=SIGN_HELP)
    async def sign_prefix_command(self, ctx: Context, *, term: str):
        await ctx.reply(**sign_impl(term))

    @slash_command(name="handshape")
    async def handshape_command(self, inter: ApplicationCommandInteraction):
        pass

    @handshape_command.sub_command(name="show")
    async def handshape_show(self, inter: ApplicationCommandInteraction, name: str):
        """Display a handshape

        Parameters
        ----------
        name: The handshape to show
        """
        await inter.response.send_message(**handshape_impl(name))

    @handshape_command.sub_command(name="random")
    async def handshape_random(self, inter: ApplicationCommandInteraction):
        """Show a random handshape"""
        await inter.response.send_message(**handshape_impl("random"))

    @handshape_show.autocomplete("name")
    async def handshape_autocomplete(
        self, inter: ApplicationCommandInteraction, name: str
    ):
        name = name.strip()
        if not name:
            return handshapes.HANDSHAPE_NAMES[:25]
        return get_close_matches(name, handshapes.HANDSHAPE_NAMES)

    @handshape_command.sub_command(name="list")
    async def handshape_list(self, inter: ApplicationCommandInteraction):
        """List handshapes"""
        await inter.response.send_message(**handshapes_impl(prefix="/"))

    @command(name="handshape", aliases=("shape",), help=HANDSHAPE_HELP)
    async def handshape_prefix_command(self, ctx: Context, name="random"):
        await ctx.reply(**handshape_impl(name))

    @command(name="handshapes", aliases=("shapes",), help="List handshapes")
    async def handshapes_prefix_command(self, ctx: Context):
        logger.info("sending handshapes list")
        await ctx.reply(**handshapes_impl(prefix=settings.COMMAND_PREFIX))


def setup(bot: Bot) -> None:
    bot.add_cog(ASL(bot))
