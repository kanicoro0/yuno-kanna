from typing import Iterable, Optional, Tuple

import discord
from discord import app_commands

from yuno.discord.ui import YunoView, permission_context, require_permission
from yuno.listening.models import ListeningChannel
from yuno.listening.service import ListeningChannelService
from yuno.permissions import ActorIdentity, PermissionLevel, PermissionService


LISTEN_LABEL = 'この場所を聞く'
REMOVE_LABEL = 'この場所を外す'
REFRESH_LABEL = '更新'


def status_text(
    listening_items: Iterable[ListeningChannel],
    call_names: Iterable[str],
    current_channel_id: Optional[str] = None,
    can_change: bool = False,
) -> str:
    items = tuple(listening_items)
    names = '、'.join(call_names)
    lines = [
        'いまの聞こえ方',
        'DMでは返す',
        '呼ばれたら返す',
    ]
    if current_channel_id is None:
        lines.append(
            '聞き耳の場所: 設定されている' if items
            else '聞き耳の場所: まだない'
        )
    else:
        current = next((
            item for item in items
            if item.discord_channel_id == current_channel_id
        ), None)
        if current is None:
            lines.append('この場所: ここでは聞いてない')
        elif current.source == 'env':
            lines.append('この場所: 聞いてる（最初から入っている場所）')
        else:
            lines.append('この場所: 聞いてる')
        if current is not None and current.source == 'env':
            lines.append('変更: この画面からは外せない')
        else:
            lines.append(
                '変更: できる' if can_change
                else '変更: 管理できる人だけ'
            )
    if names:
        lines.append(f'呼び名: {names}')
    return '\n'.join(lines)


class StatusView(YunoView):
    def __init__(
        self,
        listening: ListeningChannelService,
        call_names: Tuple[str, ...],
        permissions: PermissionService,
        *,
        opened_by_user_id: int,
        guild_id: Optional[str],
        channel_id: Optional[str],
        can_change: bool,
    ):
        super().__init__(
            opened_by_user_id=opened_by_user_id,
            permissions=permissions,
        )
        self.listening = listening
        self.call_names = call_names
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.can_change = can_change

    async def prepare(self) -> str:
        items = await self.listening.list_all()
        self._set_buttons(items)
        return status_text(
            items,
            self.call_names,
            self.channel_id,
            self.can_change,
        )

    def _set_buttons(self, items: Iterable[ListeningChannel]) -> None:
        self.clear_items()
        current = next((
            item for item in items
            if item.discord_channel_id == self.channel_id
        ), None)
        if self.channel_id is not None and self.guild_id is not None:
            if current is None:
                self.add_yuno_button(
                    label=LISTEN_LABEL,
                    custom_id='yuno:status:listen',
                    handler=self._listen_here,
                )
            elif current.source != 'env':
                self.add_yuno_button(
                    label=REMOVE_LABEL,
                    custom_id='yuno:status:remove',
                    handler=self._remove_here,
                )
        self.add_yuno_button(
            label=REFRESH_LABEL,
            custom_id='yuno:status:refresh',
            handler=self._refresh,
        )

    async def _listen_here(self, interaction: discord.Interaction) -> None:
        if not await require_permission(
            interaction, self.permissions, PermissionLevel.GUILD_ADMIN
        ):
            return
        if self.channel_id is None or self.guild_id is None:
            return
        await self.listening.add(self.channel_id, self.guild_id)
        await self._refresh(interaction)

    async def _remove_here(self, interaction: discord.Interaction) -> None:
        if not await require_permission(
            interaction, self.permissions, PermissionLevel.GUILD_ADMIN
        ):
            return
        if self.channel_id is None:
            return
        await self.listening.remove(self.channel_id)
        await self._refresh(interaction)

    async def _refresh(self, interaction: discord.Interaction) -> None:
        self.can_change = self.permissions.allows(
            ActorIdentity(interaction.user.id),
            PermissionLevel.GUILD_ADMIN,
            permission_context(interaction),
        )
        text = await self.prepare()
        await interaction.response.edit_message(content=text, view=self)


def create_status_command(
    listening: ListeningChannelService,
    call_names: Tuple[str, ...],
    permissions: PermissionService,
) -> app_commands.Command:
    @app_commands.command(name='status', description='いまの聞き方を見る')
    async def status(interaction: discord.Interaction) -> None:
        guild_id, channel_id = _text_channel_context(interaction)
        can_change = permissions.allows(
            ActorIdentity(interaction.user.id),
            PermissionLevel.GUILD_ADMIN,
            permission_context(interaction),
        )
        view = StatusView(
            listening,
            call_names,
            permissions,
            opened_by_user_id=interaction.user.id,
            guild_id=guild_id,
            channel_id=channel_id,
            can_change=can_change,
        )
        text = await view.prepare()
        await interaction.response.send_message(
            text,
            ephemeral=True,
            view=view,
        )
        original_response = getattr(interaction, 'original_response', None)
        if callable(original_response):
            try:
                view.bind_message(await original_response())
            except discord.HTTPException:
                pass

    return status


def _text_channel_context(
    interaction: discord.Interaction,
) -> Tuple[Optional[str], Optional[str]]:
    channel = getattr(interaction, 'channel', None)
    if (
        interaction.guild_id is None
        or interaction.channel_id is None
        or getattr(channel, 'type', None) != discord.ChannelType.text
    ):
        return None, None
    return str(interaction.guild_id), str(interaction.channel_id)
