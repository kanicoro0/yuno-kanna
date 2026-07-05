from typing import Iterable, Optional

import discord
from discord import app_commands

from yuno.care_marks.models import CareMark
from yuno.commands.admin_service import (
    CARE_MARK_KINDS,
    CARE_MARK_STATUS_NAMES,
    CareMarkCommandService,
)
from yuno.permissions import (
    ActorIdentity,
    DiscordPermissionContext,
    PermissionLevel,
    PermissionService,
)


def create_memories_group(
    service: CareMarkCommandService,
    permissions: PermissionService,
) -> app_commands.Group:
    group = app_commands.Group(
        name='memories',
        description='この場のCareMarkを確認・管理します',
    )

    @group.command(name='list', description='この場のCareMarkを表示します')
    async def memories_list(
        interaction: discord.Interaction,
        kind: str = 'all',
        status: str = 'visible',
        limit: app_commands.Range[int, 1, 20] = 10,
    ) -> None:
        if not await _require_admin(interaction, permissions):
            return
        if kind not in {*CARE_MARK_KINDS, 'all'}:
            await _reply(interaction, 'kindは memory / attention / all から選んでね')
            return
        if status not in {*CARE_MARK_STATUS_NAMES, 'visible', 'all'}:
            await _reply(
                interaction,
                'statusは draft / active / open / closed / hidden / visible / all から選んでね',
            )
            return
        marks = await service.list_marks(
            _channel(interaction),
            _guild(interaction),
            kind,
            status,
            limit,
        )
        await _reply(interaction, render_care_marks(marks))

    @group.command(name='add', description='この場へCareMarkを追加します')
    async def memories_add(
        interaction: discord.Interaction,
        kind: str,
        text: str,
        status: Optional[str] = None,
    ) -> None:
        if not await _require_admin(interaction, permissions):
            return
        try:
            mark = await service.add_mark(
                _channel(interaction),
                _guild(interaction),
                kind,
                text,
                status,
            )
        except ValueError:
            await _reply(interaction, 'kindかstatusがCareMarkの規則と合わないみたい')
            return
        await _reply(
            interaction,
            f'{mark.public_id} を {mark.kind}/{mark.status} で追加したよ',
        )

    @group.command(name='status', description='CareMarkの状態を変更します')
    async def memories_status(
        interaction: discord.Interaction,
        public_id: str,
        status: str,
    ) -> None:
        if not await _require_admin(interaction, permissions):
            return
        try:
            mark = await service.set_status(
                _channel(interaction),
                public_id,
                status,
            )
        except ValueError:
            await _reply(interaction, 'そのkindでは使えないstatusみたい')
            return
        await _reply(
            interaction,
            f'{public_id} を {status} にしたよ'
            if mark else
            'この場では見つからないみたい',
        )

    return group


def render_care_marks(marks: Iterable[CareMark]) -> str:
    return '\n'.join(
        f'{mark.public_id} [{mark.kind}/{mark.status}] {_preview(mark.text)}'
        for mark in marks
    ) or 'この場には該当するCareMarkはないみたい'


async def _require_admin(
    interaction: discord.Interaction,
    permissions: PermissionService,
) -> bool:
    guild_permissions = getattr(interaction.user, 'guild_permissions', None)
    allowed = permissions.allows(
        ActorIdentity(interaction.user.id),
        PermissionLevel.GUILD_ADMIN,
        DiscordPermissionContext(
            guild_id=(
                str(interaction.guild_id)
                if interaction.guild_id is not None
                else None
            ),
            is_guild_admin=bool(
                guild_permissions
                and getattr(guild_permissions, 'administrator', False)
            ),
        ),
    )
    if not allowed:
        await _reply(
            interaction,
            'この印を管理するにはownerかサーバー管理者の権限が必要です',
        )
    return allowed


def _preview(value: str) -> str:
    text = value.replace('\n', ' ').strip()
    return text if len(text) <= 80 else text[:79] + '…'


def _channel(interaction: discord.Interaction) -> str:
    if interaction.channel_id is None:
        raise ValueError('channel is unavailable')
    return str(interaction.channel_id)


def _guild(interaction: discord.Interaction) -> Optional[str]:
    return (
        str(interaction.guild_id)
        if interaction.guild_id is not None
        else None
    )


async def _reply(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.send_message(text[:2000], ephemeral=True)
