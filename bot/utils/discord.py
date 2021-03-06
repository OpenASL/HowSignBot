from typing import Union

import discord


def display_name(user: Union[discord.User, discord.Member]) -> str:
    return getattr(user, "nick", None) or user.name
