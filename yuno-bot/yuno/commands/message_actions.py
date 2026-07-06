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
CLOSE_LABEL = '閉じる'
MISSING_TARGET_TEXT = 'もう触れないみたい'

_RESULT_TEXT = {
    ('memory', 'created'): 'このメッセージを残したよ',
    ('memory', 'existing'): 'もう残してあるよ',
    ('memory', 'reopened'): 'また残したよ',
    ('attention', 'created'): 'あとで見られるように置いたよ',
    ('attention', 'existing'): 'もう置いてあるよ',
    ('attention', 'reopened'): 'また見られるようにしたよ',
}


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

    async def prepare(self, result: Optional[str] = None) -> Optional[str]:
        attention = await self.service.marks_from_message(
            str(self.target.channel.id),
            str(self.target.id),
            'attention',
        )
        if attention is None:
            return None
        self.clear_items()
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
        if any(mark.status == 'open' for mark in attention):
            self.add_yuno_button(
                label=CLOSE_LABEL,
                custom_id='yuno:selected-message:close',
                handler=self._close,
            )
        return selected_message_text(self.target.content, result)

    async def _save(self, interaction: discord.Interaction) -> None:
        await self._reuse(interaction, 'memory')

    async def _later(self, interaction: discord.Interaction) -> None:
        await self._reuse(interaction, 'attention')

    async def _reuse(
        self,
        interaction: discord.Interaction,
        kind: str,
    ) -> None:
        if not await require_permission(
            interaction, self.permissions, PermissionLevel.GUILD_ADMIN
        ):
            return
        if not await self._target_is_available():
            await respond_ephemeral(interaction, MISSING_TARGET_TEXT)
            return
        change = await self.service.reuse_mark_from_message(
            str(self.target.channel.id),
            str(self.target.id),
            kind,
        )
        if change is None:
            await respond_ephemeral(interaction, MISSING_TARGET_TEXT)
            return
        text = await self.prepare(_RESULT_TEXT[(kind, change.outcome)])
        if text is None:
            await respond_ephemeral(interaction, MISSING_TARGET_TEXT)
            return
        await interaction.response.edit_message(
            content=text,
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _close(self, interaction: discord.Interaction) -> None:
        if not await require_permission(
            interaction, self.permissions, PermissionLevel.GUILD_ADMIN
        ):
            return
        if not await self._target_is_available():
            await respond_ephemeral(interaction, MISSING_TARGET_TEXT)
            return
        change = await self.service.close_attention_from_message(
            str(self.target.channel.id),
            str(self.target.id),
        )
        if change is None:
            await respond_ephemeral(interaction, MISSING_TARGET_TEXT)
            return
        text = await self.prepare('閉じたよ')
        if text is None:
            await respond_ephemeral(interaction, MISSING_TARGET_TEXT)
            return
        await interaction.response.edit_message(
            content=text,
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
        text = await view.prepare()
        if text is None:
            await respond_ephemeral(interaction, MISSING_TARGET_TEXT)
            return
        await interaction.response.send_message(
            text,
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
