from __future__ import annotations

from contextlib import suppress

import disnake
from disnake.ext.commands import Context

from bot import settings

COMMAND_PREFIX = settings.COMMAND_PREFIX

TEMPLATE = """💡 Heads up: the `{COMMAND_PREFIX}{ctx.invoked_with}` command is being phased out. Use `{substitute}` instead.
Before:
```
{before_example}
```
After:
```
{after_example}
```
"""


async def send_deprecation_notice(
    ctx: Context, *, substitute: str, before_example: str, after_example: str
):
    if settings.SEND_DEPRECATION_MESSAGES is False:
        return
    content = TEMPLATE.format(
        COMMAND_PREFIX=COMMAND_PREFIX,
        ctx=ctx,
        substitute=substitute,
        before_example=before_example,
        after_example=after_example,
    )
    with suppress(disnake.errors.Forbidden):  # user may not allow DMs from bot
        await ctx.author.send(content=content)
