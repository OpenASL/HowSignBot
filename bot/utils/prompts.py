from __future__ import annotations

from typing import TypeVar

import discord
from discord.ext.commands import Context

T = TypeVar("T")


def _format_choices(choices: dict[T, str]) -> str:
    return "\n".join(
        (f"**{i + 1}** - {value}" for i, value in enumerate(choices.values()))
    )


async def prompt_for_choice(ctx: Context, prompt: str, choices: dict[T, str]) -> T:
    prompt_message = await ctx.send(
        f"{prompt}\nEnter one of the following choices:\n{_format_choices(choices)}"
    )

    valid_entries = {str(i + 1) for i in range(len(choices))}

    def check(m: discord.Message):
        return (
            m.author == ctx.author
            and m.channel.id == prompt_message.channel.id
            and m.content.strip() in valid_entries
        )

    response_message = await ctx.bot.wait_for("message", check=check)
    index = int(response_message.content.strip()) - 1
    return tuple(choices.keys())[index]
