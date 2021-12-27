import logging
from typing import Optional

from disnake import ApplicationCommandInteraction
from disnake.ext import commands
from disnake.ext.commands import Context

import catchphrase
from bot import settings

logger = logging.getLogger(__name__)

COMMAND_PREFIX = settings.COMMAND_PREFIX

SENTENCE_HELP = """Display a random sentence

Enter {COMMAND_PREFIX}sentence || to display the sentence in spoiler text.
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)


def sentence_impl(spoil: bool):
    sentence = catchphrase.sentence()
    if spoil:
        sentence = f"||{sentence}||"
    log = (
        f"sending random sentence in spoiler text: '{sentence}'"
        if spoil
        else f"sending random sentence: '{sentence}'"
    )
    logger.info(log)
    return {"content": sentence}


IDIOM_HELP = """Display a random English idiom

Enter {COMMAND_PREFIX}idiom || to display the idiom and its meaning in spoiler text.
""".format(
    COMMAND_PREFIX=COMMAND_PREFIX
)

IDIOM_TEMPLATE = """**{idiom}**
Meaning: {meaning}
"""

IDIOM_SPOILER_TEMPLATE = """||**{idiom}**||
Meaning: ||{meaning}||
"""


def idiom_impl(spoil: bool):
    data = catchphrase.idiom()
    log = (
        f"sending random idiom in spoiler text: {data}"
        if spoil
        else f"sending random idiom: {data}"
    )
    logger.info(log)
    template = IDIOM_SPOILER_TEMPLATE if spoil else IDIOM_TEMPLATE
    content = template.format(idiom=data["phrase"], meaning=data["meaning"])
    return {
        "content": content,
    }


class English(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(name="sentence")
    async def sentence_command(
        self, inter: ApplicationCommandInteraction, spoil: bool = True
    ):
        """Display a random sentence

        Parameters
        ----------
        spoil: Whether to use spoiler text
        """
        await inter.send(**sentence_impl(spoil))

    @commands.slash_command(name="idiom")
    async def idiom_command(
        self, inter: ApplicationCommandInteraction, spoil: bool = True
    ):
        """Display a random English idiom

        Parameters
        ----------
        spoil: Whether to use spoiler text
        """
        await inter.send(**idiom_impl(spoil))

    # Deprecated prefix commands

    @commands.command(name="sentence", help=SENTENCE_HELP)
    async def sentence_prefix_command(self, ctx: Context, spoiler: Optional[str]):
        spoil = spoiler.startswith("||") if spoiler else False
        await ctx.send(**sentence_impl(spoil))

    @commands.command(name="idiom", help=IDIOM_HELP)
    async def idiom_prefix_command(self, ctx: Context, spoiler: Optional[str]):
        spoil = spoiler.startswith("||") if spoiler else False
        await ctx.send(**idiom_impl(spoil))

    # End deprecated prefix commands


def setup(bot: commands.Bot) -> None:
    bot.add_cog(English(bot))
