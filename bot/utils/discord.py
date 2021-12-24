from typing import Union

import disnake


def display_name(user: Union[disnake.User, disnake.Member]) -> str:
    return getattr(user, "nick", None) or user.name
