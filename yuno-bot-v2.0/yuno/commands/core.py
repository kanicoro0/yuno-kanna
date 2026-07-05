from dataclasses import dataclass
from typing import Iterable, Optional

import discord
from discord import app_commands

from yuno.care_marks.models import CareMark
from yuno.commands.admin_service import (
    CARE_MARK_KINDS,
    CARE_MARK_STATUS_NAMES,
    CareMarkCommandService,
)
from yuno.discord.ui import (
    YunoView,
    require_permission,
    respond_ephemeral,
)
from yuno.permissions import (
    PermissionLevel,
    PermissionService,
)


HIDE_LABEL = '隠す'
CLOSE_LABEL = '閉じる'
RESTORE_LABEL = '戻す'
MISSING_MARK_TEXT = 'もう見つからないよ'

_STATUS_TEXT = {
    'draft': 'まだ置いてある',
    'active': '覚えている',
    'open': 'まだ開いている',
    'closed': '閉じている',
    'hidden': '隠している',
}


@dataclass(frozen=True)
class MarkAction:
    label: str
    target_status: str


def action_for_mark(mark: CareMark) -> Optional[MarkAction]:
    if mark.kind == 'memory' and mark.status == 'active':
        return MarkAction(HIDE_LABEL, 'hidden')
    if mark.kind == 'attention' and mark.status == 'open':
        return MarkAction(CLOSE_LABEL, 'closed')
    if mark.kind == 'attention' and mark.status == 'closed':
        return MarkAction(RESTORE_LABEL, 'open')
    return None


class MemoriesView(YunoView):
    def __init__(
        self,
        service: CareMarkCommandService,
        permissions: PermissionService,
        *,
        opened_by_user_id: int,
        channel_id: str,
        guild_id: Optional[str],
        kind: str,
        status: str,
        limit: int,
    ):
        super().__init__(
            opened_by_user_id=opened_by_user_id,
            permissions=permissions,
            required_permission=PermissionLevel.GUILD_ADMIN,
        )
        self.service = service
        self.permissions = permissions
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.kind = kind
        self.status = status
        self.limit = limit
        self._shown_mark_ids = frozenset()

    async def prepare(self) -> str:
        marks = await self.service.list_marks(
            self.channel_id,
            self.guild_id,
            self.kind,
            self.status,
            self.limit,
        )
        self._set_buttons(marks)
        return render_care_marks(marks)

    def _set_buttons(self, marks: Iterable[CareMark]) -> None:
        selected = tuple(marks)
        self._shown_mark_ids = frozenset(
            mark.public_id for mark in selected
        )
        self.clear_items()
        for index, mark in enumerate(selected, start=1):
            action = action_for_mark(mark)
            if action is None:
                continue

            async def change(
                interaction: discord.Interaction,
                public_id: str = mark.public_id,
                target_status: str = action.target_status,
            ) -> None:
                await self._change(interaction, public_id, target_status)

            self.add_yuno_button(
                label=f'{index} {action.label}',
                custom_id=(
                    f'yuno:memories:{mark.public_id}:{action.target_status}'
                ),
                handler=change,
            )

    async def _change(
        self,
        interaction: discord.Interaction,
        public_id: str,
        target_status: str,
    ) -> None:
        if not await require_permission(
            interaction, self.permissions, PermissionLevel.GUILD_ADMIN
        ):
            return
        if public_id not in self._shown_mark_ids:
            await respond_ephemeral(interaction, MISSING_MARK_TEXT)
            return
        try:
            mark = await self.service.set_status(
                self.channel_id,
                public_id,
                target_status,
            )
        except ValueError:
            mark = None
        if mark is None:
            await respond_ephemeral(interaction, MISSING_MARK_TEXT)
            return
        text = await self.prepare()
        await interaction.response.edit_message(content=text, view=self)


def create_memories_group(
    service: CareMarkCommandService,
    permissions: PermissionService,
) -> app_commands.Group:
    group = app_commands.Group(
        name='memories',
        description='この場に残した印を見る',
    )

    @group.command(name='list', description='この場の印を表示')
    async def memories_list(
        interaction: discord.Interaction,
        kind: str = 'all',
        status: str = 'visible',
        limit: app_commands.Range[int, 1, 20] = 10,
    ) -> None:
        if not await _require_admin(interaction, permissions):
            return
        if kind not in {*CARE_MARK_KINDS, 'all'}:
            await _reply(interaction, 'kind: memory / attention / all')
            return
        if status not in {*CARE_MARK_STATUS_NAMES, 'visible', 'all'}:
            await _reply(
                interaction,
                'status: draft / active / open / closed / hidden / visible / all',
            )
            return
        view = MemoriesView(
            service,
            permissions,
            opened_by_user_id=interaction.user.id,
            channel_id=_channel(interaction),
            guild_id=_guild(interaction),
            kind=kind,
            status=status,
            limit=limit,
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

    @group.command(name='add', description='この場に印を追加')
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
            await _reply(interaction, 'kindかstatusが合わない')
            return
        await _reply(
            interaction,
            f'{mark.public_id} [{mark.kind}/{mark.status}] を追加',
        )

    @group.command(name='status', description='印の状態を変更')
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
            await _reply(interaction, 'そのkindでは使えないstatus')
            return
        await _reply(
            interaction,
            f'{public_id} -> {status}'
            if mark else
            'この場では見つからない',
        )

    return group


def render_care_marks(marks: Iterable[CareMark]) -> str:
    return '\n'.join(
        f'{index}. {_STATUS_TEXT.get(mark.status, "置いてある")}\n'
        f'   {_preview(mark.text)}'
        for index, mark in enumerate(marks, start=1)
    ) or 'ここにはまだない'


async def _require_admin(
    interaction: discord.Interaction,
    permissions: PermissionService,
) -> bool:
    return await require_permission(
        interaction, permissions, PermissionLevel.GUILD_ADMIN
    )


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
