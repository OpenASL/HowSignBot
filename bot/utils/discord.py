import discord


def display_name(user: discord.User | discord.Member) -> str:
    return getattr(user, "nick", None) or user.name
