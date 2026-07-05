from typing import Optional

import discord
from discord import app_commands

from yuno.commands.admin_service import CareMarkCommandService
from yuno.discord.ui import (
    YunoView,
    require_permission,
    respond_ephemeral,
)
from yuno.permissions import PermissionLevel, PermissionService


CONTEXT_COMMAND_NAME = 'ゆのに預ける'
SAVE_LABEL = '残す'
LATER_LABEL = 'あとで見る'
MISSING_TARGET_TEXT = 'もう触れないみたい'


def selected_message_text(content: str, result: Optional[str] = None) -> str:
    preview = content.replace('\n', ' ').strip()
    if len(preview) > 140:
        preview = preview[:139] + '…'
    lines = ['選んだメッセージ', f'「{preview or "本文のないメッセージ"}」']
    lines.append(result or 'どうしておく？')
    return '\n'.join(lines)


class SelectedMessageView(YunoView):
    def __init__(
        self,
        service: CareMarkCommandService,
        permissions: PermissionService,
        target: discord.Message,
        *,
        opened_by_user_id: int,
    ):
        super().__init__(
            opened_by_user_id=opened_by_user_id,
            permissions=permissions,
            required_permission=PermissionLevel.GUILD_ADMIN,
        )
        self.service = service
        self.permissions = permissions
        self.target = target
        self.add_yuno_button(
            label=SAVE_LABEL,
            custom_id='yuno:selected-message:save',
            handler=self._save,
        )
        self.add_yuno_button(
            label=LATER_LABEL,
            custom_id='yuno:selected-message:later',
            handler=self._later,
        )

    async def _save(self, interaction: discord.Interaction) -> None:
        await self._apply(interaction, 'memory', 'このメッセージを残したよ')

    async def _later(self, interaction: discord.Interaction) -> None:
        await self._apply(
            interaction,
            'attention',
            'あとで見られるように置いたよ',
        )

    async def _apply(
        self,
        interaction: discord.Interaction,
        kind: str,
        result_text: str,
    ) -> None:
        if not await require_permission(
            interaction, self.permissions, PermissionLevel.GUILD_ADMIN
        ):
            return
        if not await self._target_is_available():
            await respond_ephemeral(interaction, MISSING_TARGET_TEXT)
            return
        mark = await self.service.add_mark_from_message(
            str(self.target.channel.id),
            str(self.target.id),
            kind,
        )
        if mark is None:
            await respond_ephemeral(interaction, MISSING_TARGET_TEXT)
            return
        self.clear_items()
        await interaction.response.edit_message(
            content=selected_message_text(self.target.content, result_text),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _target_is_available(self) -> bool:
        fetch_message = getattr(self.target.channel, 'fetch_message', None)
        if not callable(fetch_message):
            return False
        try:
            current = await fetch_message(self.target.id)
        except discord.HTTPException:
            return False
        return current is not None and current.id == self.target.id


def create_selected_message_command(
    service: CareMarkCommandService,
    permissions: PermissionService,
) -> app_commands.ContextMenu:
    async def selected_message(
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        if not await require_permission(
            interaction, permissions, PermissionLevel.GUILD_ADMIN
        ):
            return
        view = SelectedMessageView(
            service,
            permissions,
            message,
            opened_by_user_id=interaction.user.id,
        )
        await interaction.response.send_message(
            selected_message_text(message.content),
            ephemeral=True,
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        original_response = getattr(interaction, 'original_response', None)
        if callable(original_response):
            try:
                view.bind_message(await original_response())
            except discord.HTTPException:
                pass

    return app_commands.ContextMenu(
        name=CONTEXT_COMMAND_NAME,
        callback=selected_message,
    )
