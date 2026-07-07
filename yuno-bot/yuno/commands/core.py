from dataclasses import dataclass
from typing import Iterable, Optional

import discord
from discord import app_commands

from yuno.care.maintenance import (
    CareMaintenanceAction,
    CareMaintenanceProposal,
    CareMaintenanceService,
)
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
TIDY_STALE_TEXT = 'もう状態が変わってるみたい'

_STATUS_TEXT = {
    'draft': 'まだ置いてある',
    'active': '覚えている',
    'open': 'まだ開いている',
    'closed': '閉じている',
    'hidden': '隠している',
}

_KIND_CHOICES = [
    app_commands.Choice(name='ぜんぶ', value='all'),
    app_commands.Choice(name='残したもの', value='memory'),
    app_commands.Choice(name='あとで見るもの', value='attention'),
]

_MARK_KIND_CHOICES = [
    app_commands.Choice(name='残したもの', value='memory'),
    app_commands.Choice(name='あとで見るもの', value='attention'),
]

_STATUS_CHOICES = [
    app_commands.Choice(name='いま見るもの', value='visible'),
    app_commands.Choice(name='ぜんぶ', value='all'),
    app_commands.Choice(name='覚えている', value='active'),
    app_commands.Choice(name='まだ開いている', value='open'),
    app_commands.Choice(name='閉じている', value='closed'),
    app_commands.Choice(name='隠している', value='hidden'),
    app_commands.Choice(name='まだ置いてある', value='draft'),
]

_MARK_STATUS_CHOICES = [
    app_commands.Choice(name='まだ置いてある', value='draft'),
    app_commands.Choice(name='覚えている', value='active'),
    app_commands.Choice(name='まだ開いている', value='open'),
    app_commands.Choice(name='閉じている', value='closed'),
    app_commands.Choice(name='隠している', value='hidden'),
]

_MARK_STATUS_HELP = (
    '残したものは「まだ置いてある/覚えている/隠している」、'
    'あとで見るものは「まだ開いている/閉じている/隠している」が使えるよ'
)

_MAINTENANCE_LABELS = {
    'keep': 'そのままでよさそう',
    'close_attention': '閉じてもよさそう',
    'merge_attention': 'まとめられそう',
    'rewrite_mark_text': '短くしてもよさそう',
    'promote_draft_memory': '残してもよさそう',
    'hide_or_ignore_noisy_mark': 'いったん外してもよさそう',
}

_INTERNAL_PROPOSAL_WORDS = (
    'caremark', 'readcue', 'care_', 'public_id', 'source_message_id',
    'memory', 'attention', 'draft', 'active', 'open', 'closed', 'hidden',
    'service', 'llm', 'db',
)


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


class TidyView(YunoView):
    def __init__(
        self,
        maintenance: CareMaintenanceService,
        permissions: PermissionService,
        proposal: CareMaintenanceProposal,
        *,
        opened_by_user_id: int,
    ):
        super().__init__(
            opened_by_user_id=opened_by_user_id,
            permissions=permissions,
            required_permission=PermissionLevel.GUILD_ADMIN,
        )
        self.maintenance = maintenance
        self.permissions = permissions
        self.proposal = proposal
        self._shown_actions = tuple(proposal.actions)
        self._set_buttons()

    def _set_buttons(self) -> None:
        self.clear_items()
        for index, action in enumerate(self._shown_actions, start=1):
            if action.action != 'close_attention':
                continue

            async def apply(
                interaction: discord.Interaction,
                selected: CareMaintenanceAction = action,
            ) -> None:
                await self._apply(interaction, selected)

            self.add_yuno_button(
                label=f'{index} 閉じる',
                custom_id=f'yuno:tidy:close:{index}',
                handler=apply,
            )

    async def _apply(
        self,
        interaction: discord.Interaction,
        action: CareMaintenanceAction,
    ) -> None:
        if not await require_permission(
            interaction, self.permissions, PermissionLevel.GUILD_ADMIN
        ):
            return
        if self.is_stale or action not in self._shown_actions:
            await respond_ephemeral(interaction, TIDY_STALE_TEXT)
            return
        result = await self.maintenance.apply_selected(
            self.proposal.stream_id, action
        )
        self._stale = True
        self.clear_items()
        if result.applied:
            text = '閉じたよ\n\n整理案は、もう一度開くと更新されるよ'
        else:
            text = f'{TIDY_STALE_TEXT}\n\n整理案をもう一度開いてね'
        await interaction.response.edit_message(content=text, view=self)


def create_memories_group(
    service: CareMarkCommandService,
    permissions: PermissionService,
    maintenance: Optional[CareMaintenanceService] = None,
) -> app_commands.Group:
    group = app_commands.Group(
        name='memories',
        description='この場に残した印を見る',
    )

    @group.command(name='list', description='この場所に残したものを見る')
    @app_commands.describe(
        kind='見るものの種類',
        status='いまの状態で絞る',
        limit='表示する件数（1〜20）',
    )
    @app_commands.choices(kind=_KIND_CHOICES, status=_STATUS_CHOICES)
    async def memories_list(
        interaction: discord.Interaction,
        kind: str = 'all',
        status: str = 'visible',
        limit: app_commands.Range[int, 1, 20] = 10,
    ) -> None:
        if not await _require_admin(interaction, permissions):
            return
        if kind not in {*CARE_MARK_KINDS, 'all'}:
            await _reply(interaction, '種類は表示される選択肢から選んでね')
            return
        if status not in {*CARE_MARK_STATUS_NAMES, 'visible', 'all'}:
            await _reply(interaction, '状態は表示される選択肢から選んでね')
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

    @group.command(name='tidy', description='この場所に残したものの整理案を見る')
    async def memories_tidy(interaction: discord.Interaction) -> None:
        if not await _require_admin(interaction, permissions):
            return
        if maintenance is None:
            await _reply(interaction, '整理案はまだ開けないよ')
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        stream = await service.stream(
            _channel(interaction), _guild(interaction)
        )
        if stream is None:
            await interaction.edit_original_response(
                content=render_maintenance_proposal(CareMaintenanceProposal(0))
            )
            return
        proposal = await maintenance.propose_for_stream(stream.id)
        marks = await service.list_marks(
            _channel(interaction), _guild(interaction), 'all', 'all', 20
        )
        text = render_maintenance_proposal(proposal, marks)
        view = TidyView(
            maintenance,
            permissions,
            proposal,
            opened_by_user_id=interaction.user.id,
        )
        if not view.children:
            await interaction.edit_original_response(content=text)
            return
        message = await interaction.edit_original_response(
            content=text, view=view
        )
        view.bind_message(message)

    @group.command(name='add', description='この場に印を追加')
    @app_commands.describe(
        kind='残したものか、あとで見るもの',
        text='残す内容（500文字まで）',
        status='省略すると種類に合う初期状態になる',
    )
    @app_commands.choices(kind=_MARK_KIND_CHOICES, status=_MARK_STATUS_CHOICES)
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
            await _reply(interaction, _MARK_STATUS_HELP)
            return
        await _reply(
            interaction,
            (
                f'`{mark.public_id}` を追加\n'
                f'{_kind_label(mark.kind)} / {_status_label(mark.status)}\n'
                f'{_preview(mark.text)}'
            ),
        )

    @group.command(name='status', description='印の状態を変更')
    @app_commands.describe(
        public_id='/memories list に出ているID',
        status='変更後の状態',
    )
    @app_commands.choices(status=_MARK_STATUS_CHOICES)
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
            await _reply(interaction, _MARK_STATUS_HELP)
            return
        await _reply(
            interaction,
            (
                f'`{public_id}` を {_status_label(status)} にした'
                if mark else
                'この場では見つからない'
            ),
        )

    return group


def render_care_marks(marks: Iterable[CareMark]) -> str:
    return '\n'.join(
        f'{index}. `{mark.public_id}` {_STATUS_TEXT.get(mark.status, "置いてある")}\n'
        f'   {_preview(mark.text)}'
        for index, mark in enumerate(marks, start=1)
    ) or 'ここにはまだない'


def render_maintenance_proposal(
    proposal: CareMaintenanceProposal,
    marks: Iterable[CareMark] = (),
) -> str:
    if not proposal.actions:
        return '整理案\nいまは特にないよ'
    rows = []
    by_public = {mark.public_id: mark for mark in marks}
    for index, action in enumerate(proposal.actions, start=1):
        label = _MAINTENANCE_LABELS.get(action.action)
        if label is None:
            continue
        detail = _maintenance_detail(action, by_public)
        rows.append(f'{index}. {label}\n   {detail}')
    return '整理案\n' + ('\n\n'.join(rows) or 'いまは特にないよ')


def _maintenance_detail(
    action: CareMaintenanceAction,
    by_public: dict,
) -> str:
    target_texts = tuple(
        text
        for public_id in action.target_public_ids
        for mark in (by_public.get(public_id),)
        if mark is not None
        for text in (_safe_proposal_text(mark.text),)
        if text
    )
    if action.action == 'merge_attention':
        if target_texts:
            examples = '、'.join(f'「{text}」' for text in target_texts[:2])
            return f'{examples}など、似たものが{len(action.target_public_ids)}件'
        return f'似たものが{len(action.target_public_ids)}件あるみたい'
    if action.action == 'rewrite_mark_text' and action.proposed_text:
        proposed = _safe_proposal_text(action.proposed_text)
        if proposed:
            if target_texts:
                return f'「{target_texts[0]}」→「{proposed}」'
            return f'「{proposed}」'
    if target_texts:
        return {
            'keep': f'「{target_texts[0]}」は今のまま残せそう',
            'close_attention': (
                f'「{target_texts[0]}」はひと区切りついているかもしれない'
            ),
            'promote_draft_memory': (
                f'「{target_texts[0]}」は残しておく候補になりそう'
            ),
            'hide_or_ignore_noisy_mark': (
                f'「{target_texts[0]}」はいったん表から外してもよさそう'
            ),
        }.get(action.action, '少し見直せそう')
    return {
        'keep': '今のまま残せそう',
        'close_attention': 'ひと区切りついているかもしれない',
        'rewrite_mark_text': '言い方を少し整えられそう',
        'promote_draft_memory': '残しておく候補になりそう',
        'hide_or_ignore_noisy_mark': 'いったん表から外してもよさそう',
    }.get(action.action, '少し見直せそう')


def _safe_proposal_text(value: str) -> str:
    text = _preview(value)
    lowered = text.casefold()
    if any(word in lowered for word in _INTERNAL_PROPOSAL_WORDS):
        return ''
    return text


def _kind_label(kind: str) -> str:
    return {
        'memory': '残したもの',
        'attention': 'あとで見るもの',
    }.get(kind, kind)


def _status_label(status: str) -> str:
    return _STATUS_TEXT.get(status, status)


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
