from __future__ import annotations

from functools import partial
from typing import Any
from typing import TypeVar

import disnake

T = TypeVar("T")


class BaseButtonGroupView(disnake.ui.View):
    def __init__(self, creator_id: int):
        super().__init__()
        self.creator_id = creator_id
        self.value: Any | None = None

    async def wait_for_value(self) -> T | None:
        await self.wait()
        return self.value


def make_button_group_view(creator_id: int, options: dict) -> BaseButtonGroupView:
    attrs = {}
    for i, (label, button_config) in enumerate(options.items()):
        config = button_config.copy()
        value = config.pop("value")

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
            label=label, style=disnake.ButtonStyle.grey, **config
        )

        attrs[callback_name] = decorator(method)

    view_class = type("GeneratedButtonGroupView", (BaseButtonGroupView,), attrs)
    return view_class(creator_id=creator_id)
