import logging
from typing import Awaitable, Callable, Optional, Union

import discord

from yuno.permissions import (
    ActorIdentity,
    DiscordPermissionContext,
    PermissionLevel,
    PermissionService,
)


logger = logging.getLogger(__name__)

EPHEMERAL_TEXT_LIMIT = 500
STALE_TEXT = 'もう閉じてるよ'
DENIED_TEXT = 'ここは触れないみたい'
OWNER_TEXT = 'これは開いた人だけ触れるよ'

ButtonHandler = Callable[[discord.Interaction], Awaitable[None]]


def short_ephemeral_text(text: str) -> str:
    selected = text.strip() or 'うん'
    if len(selected) <= EPHEMERAL_TEXT_LIMIT:
        return selected
    return selected[:EPHEMERAL_TEXT_LIMIT - 1] + '…'


async def respond_ephemeral(
    interaction: discord.Interaction,
    text: str,
) -> bool:
    content = short_ephemeral_text(text)
    try:
        if interaction.response.is_done():
            await interaction.edit_original_response(content=content)
        else:
            await interaction.response.send_message(content, ephemeral=True)
    except discord.HTTPException:
        logger.debug('Ephemeral interaction response was no longer available')
        return False
    return True


def permission_context(
    interaction: discord.Interaction,
) -> DiscordPermissionContext:
    guild_permissions = getattr(interaction.user, 'guild_permissions', None)
    return DiscordPermissionContext(
        guild_id=(
            str(interaction.guild_id)
            if interaction.guild_id is not None
            else None
        ),
        is_guild_admin=bool(
            guild_permissions
            and getattr(guild_permissions, 'administrator', False)
        ),
    )


async def require_permission(
    interaction: discord.Interaction,
    permissions: PermissionService,
    required: PermissionLevel,
) -> bool:
    allowed = permissions.allows(
        ActorIdentity(interaction.user.id),
        required,
        permission_context(interaction),
    )
    if not allowed:
        await respond_ephemeral(interaction, DENIED_TEXT)
    return allowed


class YunoButton(discord.ui.Button['YunoView']):
    def __init__(
        self,
        *,
        label: str,
        custom_id: str,
        handler: ButtonHandler,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
    ):
        super().__init__(label=label, custom_id=custom_id, style=style)
        self._handler = handler

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._handler(interaction)


class YunoView(discord.ui.View):
    def __init__(
        self,
        *,
        timeout: Optional[float] = 120.0,
        opened_by_user_id: Optional[Union[str, int]] = None,
        permissions: Optional[PermissionService] = None,
        required_permission: PermissionLevel = PermissionLevel.USER,
    ):
        if required_permission > PermissionLevel.USER and permissions is None:
            raise ValueError('guarded views require PermissionService')
        super().__init__(timeout=timeout)
        self.opened_by_user_id = (
            str(opened_by_user_id) if opened_by_user_id is not None else None
        )
        self.permissions = permissions
        self.required_permission = required_permission
        self._message: Optional[discord.Message] = None
        self._stale = False

    @property
    def is_stale(self) -> bool:
        return self._stale

    def bind_message(self, message: discord.Message) -> None:
        self._message = message

    def add_yuno_button(
        self,
        *,
        label: str,
        custom_id: str,
        handler: ButtonHandler,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
    ) -> YunoButton:
        button = YunoButton(
            label=label,
            custom_id=custom_id,
            handler=handler,
            style=style,
        )
        self.add_item(button)
        return button

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self._stale:
            await respond_ephemeral(interaction, STALE_TEXT)
            return False
        if (
            self.opened_by_user_id is not None
            and str(interaction.user.id) != self.opened_by_user_id
        ):
            await respond_ephemeral(interaction, OWNER_TEXT)
            return False
        if self.permissions is not None:
            return await require_permission(
                interaction,
                self.permissions,
                self.required_permission,
            )
        return True

    async def on_timeout(self) -> None:
        self._stale = True
        for item in self.children:
            if hasattr(item, 'disabled'):
                item.disabled = True
        if self._message is None:
            return
        try:
            await self._message.edit(view=self)
        except Exception:
            logger.debug('Timed-out view could not be refreshed', exc_info=True)
