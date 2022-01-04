# https://github.com/MusicOnline/Botto/blob/master/botto/modules/help.py
import inspect
from typing import Any, Dict, List, Optional

import disnake
import yaml
from disnake.ext import commands

from bot import settings

BotMapping = Dict[Optional[commands.Cog], List[commands.Command]]

COMMAND_PREFIX = settings.COMMAND_PREFIX


class HelpCommand(commands.HelpCommand):
    def __init__(self, **options: Any) -> None:
        self.color = disnake.Embed.Empty
        super().__init__(**options)

    async def filter_commands(
        self, cmds, *, sort=False, key=None
    ):  # pylint: disable=arguments-differ
        """Filter out disabled commands even if verify_checks is False."""
        cmds = await super().filter_commands(cmds, sort=sort, key=key)
        return [command for command in cmds if command.enabled]

    async def get_bot_help(self, mapping: BotMapping) -> List[disnake.Embed]:
        embeds: List[disnake.Embed] = []
        last_embed = None
        last_cog = None
        last_content = None
        for cog, cmds in mapping.items():
            cmds = await self.filter_commands(cmds)
            if not cog or not cmds:
                continue
            if last_embed is None:
                embed = disnake.Embed(color=self.color)
            else:
                embed = last_embed  # type: ignore
            if last_content:
                embed.add_field(name=last_cog, value=last_content, inline=False)  # type: ignore
                last_cog = None
                last_content = None
            content = "\n".join(
                f"`{COMMAND_PREFIX}{cmd}` — {cmd.short_doc}" for cmd in cmds
            )
            if len(content) > 1024:
                content = (
                    f"There are {len(cmds)} commands available. Type "
                    f"`{COMMAND_PREFIX}{self.invoked_with} {cog.qualified_name}` "
                    f"to learn more."
                )
            before = embed.copy()
            embed.add_field(name=cog.qualified_name, value=content, inline=False)
            if len(embed) > 6000:
                embeds.append(before)
                last_embed = None
                last_cog = cog.qualified_name
                last_content = content
            else:
                last_embed = embed
        embeds.append(last_embed)
        return embeds

    async def send_bot_help(self, mapping: BotMapping) -> List[disnake.Message]:
        messages = []
        embeds = await self.get_bot_help(mapping)
        for embed in embeds:
            msg = await self.context.reply(embed=embed)
            messages.append(msg)
        return messages

    async def make_cog_embed(self, cog: commands.Cog) -> Optional[disnake.Embed]:
        docstring = inspect.getdoc(cog)
        if not docstring:
            return None
        items = yaml.full_load(docstring.format(cog=cog))  # value substitution
        if not isinstance(items, dict):
            # For docstrings without format (eg. third party commands like jishaku)
            return None
        embed = disnake.Embed(
            color=items.pop("color", self.color),
            description=items.pop("description", "No description available."),
        )
        embed.set_author(name=items.pop("name", cog.qualified_name))
        embed.set_footer(text=items.pop("footer", ""))
        embed.set_thumbnail(url=items.pop("thumbnail", ""))
        embed.set_image(url=items.pop("image", ""))
        items.pop("short", None)
        for key, value in items.items():
            inline = key.endswith(" (inline)")
            if inline:
                key = key[:-9]
            embed.add_field(name=key, value=value, inline=inline)
        return embed

    async def get_cog_help(self, cog: commands.Cog) -> List[disnake.Embed]:
        """Return one or two embeds for cog help in a list.

        First embed is the cog's help embed (or formatted docstring) if any.
        If there is enough space, all commands will be in the first embed.
        Otherwise, second embed is all commands.

        If the docstring is unformatted, one embed will be returned.
        Its description will be the cog description, fields are all commands.

        Assumption: Second or only embed's total character count does not exceed 6000.
        """
        embeds: List[disnake.Embed] = []
        if hasattr(cog, "_help_embed_func"):
            embed = await cog.get_help_embed(self)
            embeds.append(embed)
        else:
            embed = await self.make_cog_embed(cog)
            if embed:
                embeds.append(embed)
        cmds = await self.filter_commands(cog.get_commands())
        if not cmds:
            error = self.command_not_found(cog.qualified_name)
            await self.send_error_message(error)
            return []
        if embeds:
            before = embed.copy()
        else:
            embed = disnake.Embed(
                color=self.color, description=cog.description or disnake.Embed.Empty
            )
            embed.set_author(name=cog.qualified_name)

        self.add_command_fields(cmds, embed)
        if len(embed) > 6000 and embeds:
            embeds[0] = before
            embed = disnake.Embed(
                color=before.color, description=cog.description or disnake.Embed.Empty
            )
            embed.set_author(name=cog.qualified_name)
            self.add_command_fields(cmds, embed)
            embeds.append(embed)
        elif not embeds:
            embeds.append(embed)
        return embeds

    def add_command_fields(
        self, cmds: List[commands.Command], embed: disnake.Embed
    ) -> None:
        last_start_index = 0
        last_content: List[str] = []
        for i, cmd in enumerate(cmds):
            content = f"`{COMMAND_PREFIX}{cmd}` — {cmd.short_doc}"
            if len("\n".join(last_content + [content])) <= 1024:
                last_content.append(content)
            else:
                embed.add_field(
                    name=f"Commands ({last_start_index + 1}-{i}/{len(cmds)})",
                    value="\n".join(last_content),
                    inline=False,
                )
                last_start_index = i
                last_content = [content]
            if i == len(cmds) - 1 and last_start_index == 0:
                embed.add_field(
                    name="Commands", value="\n".join(last_content), inline=False
                )
            elif i == len(cmds) - 1:
                embed.add_field(
                    name=f"Commands ({last_start_index + 1}-{i + 1}/{len(cmds)})",
                    value="\n".join(last_content),
                    inline=False,
                )

    async def send_cog_help(self, cog: commands.Cog) -> List[disnake.Message]:
        # cog cannot be None apparently
        messages = []
        embeds = await self.get_cog_help(cog)
        for embed in embeds:
            msg = await self.context.reply(embed=embed)
            messages.append(msg)
        return messages

    async def make_command_embed(self, command: commands.Command) -> disnake.Embed:
        docstring = inspect.getdoc(command.callback)
        if not docstring:
            embed = disnake.Embed(color=self.color, description=command.help)
            embed.set_author(name=f"{COMMAND_PREFIX}{command} {command.signature}")
            if command.aliases:
                embed.add_field(
                    name="Aliases", value=" // ".join(command.aliases), inline=False
                )
            return embed
        items = yaml.full_load(docstring.format(command=command))  # value substitution
        if not isinstance(items, dict):
            # For docstrings without format (eg. third party commands like jishaku)
            embed = disnake.Embed(color=self.color, description=docstring)
            embed.set_author(name=f"{COMMAND_PREFIX}{command} {command.signature}")
            if command.aliases:
                embed.add_field(
                    name="Aliases", value=" // ".join(command.aliases), inline=False
                )
        else:
            embed = disnake.Embed(
                color=items.pop("color", self.color),
            )
            embed.set_author(
                name=items.pop("name", f"{COMMAND_PREFIX}{command} {command.signature}")
            )
            embed.set_footer(text=items.pop("footer", disnake.Embed.Empty))
            embed.set_thumbnail(url=items.pop("thumbnail", ""))
            embed.set_image(url=items.pop("image", ""))
            items.pop("short", None)
            for key, value in items.items():
                inline = key.endswith(" (inline)")
                if inline:
                    key = key[:-9]
                embed.add_field(name=key, value=value, inline=inline)
            if command.aliases and items.pop("add_aliases", True):
                embed.add_field(
                    name="Aliases", value=" // ".join(command.aliases), inline=False
                )
        return embed

    async def get_command_help(self, command: commands.Command) -> disnake.Embed:
        """Return one embed for command help.

        Assumption: Embed's total character count does not exceed 6000.
        """
        if getattr(command, "_help_embed_func", False):
            embed = await command.get_help_embed(self)
        else:
            embed = await self.make_command_embed(command)
        if not isinstance(command, commands.Group):
            return embed

        # Subcommand list handling
        cmds = await self.filter_commands(command.commands)
        last_start_index = 0
        last_content: List[str] = []
        for i, cmd in enumerate(cmds):
            content = f"`{COMMAND_PREFIX}{cmd}` — {cmd.short_doc}"
            if len("\n".join(last_content + [content])) <= 1024:
                last_content.append(content)
            else:
                embed.add_field(
                    name=f"Subcommands ({last_start_index + 1}-{i}/{len(cmds)})",
                    value="\n".join(last_content),
                    inline=False,
                )
                last_start_index = i
                last_content = [content]
            if i == len(cmds) - 1 and last_start_index == 0:
                embed.add_field(
                    name="Subcommands", value="\n".join(last_content), inline=False
                )
            elif i == len(cmds) - 1:
                embed.add_field(
                    name=f"Subcommands ({last_start_index + 1}-{i + 1}/{len(cmds)})",
                    value="\n".join(last_content),
                    inline=False,
                )
        return embed

    async def send_command_help(self, command: commands.Command) -> disnake.Message:
        embed = await self.get_command_help(command)
        return await self.context.reply(embed=embed)

    async def send_group_help(self, group: commands.Group) -> disnake.Message:
        return await self.send_command_help(group)

    def command_not_found(self, string: str) -> str:
        return f"No command called `{string}` found."

    def subcommand_not_found(self, command: commands.Command, string: str) -> str:
        if isinstance(command, commands.Group) and command.all_commands:
            return (
                f"Command `{command.qualified_name}` has no subcommand named `{string}`."
            )
        return f"Command `{command.qualified_name}` has no subcommands."

    async def send_error_message(self, error: str) -> disnake.Message:
        return await self.context.reply(error)


def setup(bot) -> None:
    bot._old_help_command = bot.help_command
    bot.help_command = HelpCommand(
        verify_checks=False,
        command_attrs={"help": "Show help information."},
    )


def teardown(bot) -> None:
    bot.help_command = bot._old_help_command
    del bot._old_help_command
