from typing import Union

import disnake

THEME_COLOR = disnake.Color.from_rgb(132, 196, 208)


def display_name(user: Union[disnake.User, disnake.Member]) -> str:
    return getattr(user, "nick", None) or user.name
