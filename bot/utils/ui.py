from __future__ import annotations

from functools import partial
from typing import Any
from typing import Callable
from typing import Coroutine
from typing import NamedTuple
from typing import Sequence
from typing import TypeVar

import disnake

T = TypeVar("T")


class ButtonGroupOption(NamedTuple):
    label: str
    value: Any
    emoji: str | None = None


class ButtonGroupView(disnake.ui.View):
    def __init__(self, creator_id: int):
        super().__init__()
        self.creator_id = creator_id
        self.value: Any | None = None

    async def wait_for_value(self) -> T | None:
        await self.wait()
        return self.value

    @classmethod
    def from_options(
        cls, options: Sequence[ButtonGroupOption], *, creator_id: int
    ) -> ButtonGroupView:
        attrs = {}
        for i, (label, value, emoji) in enumerate(options):

            async def callback(
                self,
                button: disnake.ui.Button,
                inter: disnake.MessageInteraction,
                *,
                value: T,
            ):
                # Ignore clicks by other users
                if inter.user.id != self.creator_id:
                    return
                self.value = value
                button.style = disnake.ButtonStyle.blurple
                # Disable buttons
                for child in self.children:
                    if isinstance(child, disnake.ui.Button):
                        child.disabled = True
                await inter.response.edit_message(view=self)
                self.stop()

            callback_name = f"callback_{i}"
            method = partial(callback, value=value)
            method.__name__ = callback_name  # type: ignore
            decorator = disnake.ui.button(
                label=label,
                style=disnake.ButtonStyle.grey,
                emoji=emoji,
            )

            attrs[callback_name] = decorator(method)

        view_class = type("GeneratedButtonGroupView", (cls,), attrs)
        return view_class(creator_id=creator_id)


Callback = Callable[[disnake.MessageInteraction, Any], Coroutine]


class Dropdown(disnake.ui.Select):
    def __init__(
        self,
        *,
        options: Sequence[disnake.SelectOption],
        on_select: Callback,
        placeholder: str | None = None,
    ):
        self.on_select = on_select

        super().__init__(
            options=options,
            placeholder=placeholder,
            min_values=1,
            max_values=1,
        )

    async def callback(self, inter: disnake.MessageInteraction):
        await self.on_select(inter, self.values[0])


class DropdownView(disnake.ui.View):
    def __init__(self):
        super().__init__()
        self.dropdown: Dropdown | None = None

    @classmethod
    def from_options(
        cls,
        *,
        options: Sequence[disnake.SelectOption],
        on_select: Callback,
        placeholder: str | None = None,
    ) -> DropdownView:
        view = cls()

        async def handle_select(inter: disnake.MessageInteraction, value):
            await on_select(inter, value)
            view.stop()

        dropdown = Dropdown(
            options=options, on_select=handle_select, placeholder=placeholder
        )
        view.add_item(dropdown)
        view.dropdown = dropdown
        return view
