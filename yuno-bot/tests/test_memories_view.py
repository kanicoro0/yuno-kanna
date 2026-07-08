from types import SimpleNamespace
import unittest

from yuno.care.maintenance import (
    CareMaintenanceAction,
    CareMaintenanceApplyResult,
    CareMaintenanceProposal,
)
from yuno.care_marks.models import CareMark
from yuno.commands.core import (
    CLOSE_LABEL,
    DEFAULT_MEMORIES_KIND,
    DEFAULT_MEMORIES_STATUS,
    HIDE_LABEL,
    MemoriesView,
    create_memories_group,
    render_care_marks,
    render_maintenance_proposal,
)
from yuno.discord.ui import DENIED_TEXT
from yuno.permissions import PermissionService


def mark(public_id='care_0001', kind='memory', status='active', text='残している言葉'):
    return CareMark(
        id=1,
        public_id=public_id,
        stream_id=1,
        source_message_id=None,
        kind=kind,
        status=status,
        text=text,
        created_at='now',
        updated_at='now',
    )


class FakeResponse:
    def __init__(self):
        self.sent = []
        self.edits = []
        self.deferred = []
        self._done = False

    def is_done(self):
        return self._done

    async def send_message(self, content, **kwargs):
        self.sent.append((content, kwargs))
        self._done = True

    async def edit_message(self, **kwargs):
        self.edits.append(kwargs)
        self._done = True

    async def defer(self, **kwargs):
        self.deferred.append(kwargs)
        self._done = True


class FakeInteraction:
    def __init__(self, *, administrator=True):
        self.user = SimpleNamespace(
            id=7,
            guild_permissions=SimpleNamespace(administrator=administrator),
        )
        self.channel_id = 10
        self.guild_id = 1
        self.response = FakeResponse()
        self.edited_original = []
        self._original_response = SimpleNamespace()

    async def edit_original_response(self, **kwargs):
        self.edited_original.append(kwargs)
        return self._original_response

    async def original_response(self):
        return self._original_response


class FakeService:
    def __init__(self, marks=()):
        self.marks = tuple(marks)
        self.calls = []

    async def list_marks(self, channel_id, guild_id, kind='all', status='visible', limit=10):
        self.calls.append(('list_marks', channel_id, guild_id, kind, status, limit))
        selected = tuple(self.marks)
        if kind != 'all':
            selected = tuple(mark for mark in selected if mark.kind == kind)
        if status == 'visible':
            selected = tuple(
                mark for mark in selected
                if (mark.kind, mark.status) in {('memory', 'active'), ('attention', 'open')}
            )
        elif status != 'all':
            selected = tuple(mark for mark in selected if mark.status == status)
        return selected[:limit]

    async def set_status(self, channel_id, public_id, status):
        self.calls.append(('set_status', channel_id, public_id, status))
        self.marks = tuple(
            mark if mark.public_id != public_id else CareMark(
                id=mark.id,
                public_id=mark.public_id,
                stream_id=mark.stream_id,
                source_message_id=mark.source_message_id,
                kind=mark.kind,
                status=status,
                text=mark.text,
                created_at=mark.created_at,
                updated_at='changed',
                last_touched_at=mark.last_touched_at,
            )
            for mark in self.marks
        )
        return next((mark for mark in self.marks if mark.public_id == public_id), None)

    async def stream(self, channel_id, guild_id):
        self.calls.append(('stream', channel_id, guild_id))
        return SimpleNamespace(id=1)


class FakeMaintenance:
    def __init__(self, proposal=None):
        self.proposal = proposal or CareMaintenanceProposal(1)
        self.calls = []

    async def propose_for_stream(self, stream_id):
        self.calls.append(('propose_for_stream', stream_id))
        return self.proposal

    async def apply_selected(self, stream_id, action):
        self.calls.append(('apply_selected', stream_id, action.action))
        return CareMaintenanceApplyResult(applied=True, reason='closed')


def button(view, suffix):
    return next(item for item in view.children if item.label.endswith(suffix))


class MemoriesViewTests(unittest.IsolatedAsyncioTestCase):
    async def open_list(self, service, interaction, **options):
        group = create_memories_group(service, PermissionService())
        command = group.get_command('list')
        await command.callback(
            interaction,
            options.get('kind', DEFAULT_MEMORIES_KIND),
            options.get('status', DEFAULT_MEMORIES_STATUS),
            options.get('limit', 10),
        )
        return interaction.response.sent[0][1].get('view')

    def test_renderer_uses_natural_rows_with_public_ids(self):
        text = render_care_marks((
            mark('care_0001', 'memory', 'active', '青い花'),
            mark('care_0002', 'attention', 'open', '続きの話'),
        ))

        self.assertIn('1. `care_0001` 覚えている', text)
        self.assertIn('2. `care_0002` まだ開いている', text)
        for internal in (
            'CareMark', 'ReadCue', 'memory', 'attention', 'active', 'open',
        ):
            self.assertNotIn(internal, text)

    def test_tidy_is_registered_under_memories_group(self):
        group = create_memories_group(FakeService(), PermissionService())

        self.assertIsNotNone(group.get_command('tidy'))

    def test_tidy_renderer_uses_only_user_facing_wording(self):
        proposal = CareMaintenanceProposal(1, (
            CareMaintenanceAction(
                'close_attention', ('care_0001',), reason='resolved'
            ),
            CareMaintenanceAction(
                'merge_attention', ('care_0002', 'care_0003')
            ),
            CareMaintenanceAction(
                'rewrite_mark_text',
                ('care_0004',),
                proposed_text='星の話を続ける',
            ),
        ))

        text = render_maintenance_proposal(proposal, (
            mark('care_0001', 'attention', 'open', '終わった話'),
        ))

        self.assertIn('整理案', text)
        self.assertIn('ひと区切り', text)
        self.assertIn('似たもの', text)
        self.assertIn('星の話を続ける', text)
        for internal in ('care_', 'resolved', 'close_attention', 'memory', 'attention'):
            self.assertNotIn(internal, text)

    def test_tidy_renderer_filters_internal_proposed_text(self):
        proposal = CareMaintenanceProposal(1, (
            CareMaintenanceAction(
                'rewrite_mark_text',
                ('care_0001',),
                proposed_text='care_0001 active memory',
            ),
        ))

        text = render_maintenance_proposal(proposal)

        self.assertIn('言い方を少し整えられそう', text)
        self.assertNotIn('care_0001', text)
        self.assertNotIn('active', text)

    async def test_action_for_memory_active_is_hide(self):
        view = MemoriesView(
            FakeService(), PermissionService(), opened_by_user_id=7,
            channel_id='10', guild_id='1', kind='all', status='visible', limit=10,
        )

        self.assertIsNotNone(view)

    async def test_list_rejects_invalid_filters_before_service_read(self):
        service = FakeService()
        group = create_memories_group(service, PermissionService())
        command = group.get_command('list')

        invalid_kind = FakeInteraction(administrator=True)
        await command.callback(invalid_kind, 'weird', 'visible', 10)
        self.assertEqual(
            invalid_kind.response.sent[0][0],
            '種類は表示される選択肢から選んでね',
        )

        invalid_status = FakeInteraction(administrator=True)
        await command.callback(invalid_status, 'all', 'unknown', 10)
        self.assertEqual(
            invalid_status.response.sent[0][0],
            '状態は表示される選択肢から選んでね',
        )
        self.assertEqual(service.calls, [])

    async def test_list_defaults_to_remembered_memory_surface(self):
        service = FakeService((
            mark('care_0001', 'memory', 'active'),
            mark('care_0002', 'attention', 'open'),
            mark('care_0003', 'memory', 'draft'),
        ))
        interaction = FakeInteraction(administrator=True)

        view = await self.open_list(service, interaction)

        text, kwargs = interaction.response.sent[0]
        self.assertTrue(kwargs['ephemeral'])
        self.assertIs(kwargs['view'], view)
        self.assertEqual([item.label for item in view.children], [f'1 {HIDE_LABEL}'])
        self.assertIn('care_0001', text)
        self.assertNotIn('care_0002', text)
        self.assertNotIn('care_0003', text)
        self.assertEqual(service.calls[0], (
            'list_marks', '10', '1', 'memory', 'active', 10,
        ))

    async def test_list_can_explicitly_show_open_attention(self):
        service = FakeService((
            mark('care_0001', 'memory', 'active'),
            mark('care_0002', 'attention', 'open'),
        ))
        interaction = FakeInteraction(administrator=True)

        view = await self.open_list(
            service, interaction, kind='attention', status='open'
        )

        text, kwargs = interaction.response.sent[0]
        self.assertTrue(kwargs['ephemeral'])
        self.assertIs(kwargs['view'], view)
        self.assertEqual([item.label for item in view.children], [f'1 {CLOSE_LABEL}'])
        self.assertNotIn('care_0001', text)
        self.assertIn('care_0002', text)
        self.assertEqual(service.calls[0], (
            'list_marks', '10', '1', 'attention', 'open', 10,
        ))

    async def test_non_admin_list_has_no_panel_or_service_read(self):
        service = FakeService((mark('care_0001', 'memory', 'active'),))
        interaction = FakeInteraction(administrator=False)

        view = await self.open_list(service, interaction)

        self.assertIsNone(view)
        self.assertEqual(service.calls, [])
        self.assertEqual(interaction.response.sent[0][0], DENIED_TEXT)

    async def test_button_uses_existing_status_service_then_refreshes(self):
        service = FakeService((mark('care_0001', 'memory', 'active'),))
        opening = FakeInteraction(administrator=True)
        view = await self.open_list(service, opening)
        click = FakeInteraction(administrator=True)

        await button(view, HIDE_LABEL).callback(click)

        self.assertIn(
            ('set_status', '10', 'care_0001', 'hidden'), service.calls
        )
        self.assertEqual(click.response.sent, [])
        self.assertEqual(click.response.edits[0]['content'], 'ここにはまだない')

    async def test_button_rejects_non_admin_without_service_call(self):
        service = FakeService((mark('care_0001', 'memory', 'active'),))
        opening = FakeInteraction(administrator=True)
        view = await self.open_list(service, opening)
        click = FakeInteraction(administrator=False)

        await button(view, HIDE_LABEL).callback(click)

        self.assertNotIn(
            ('set_status', '10', 'care_0001', 'hidden'), service.calls
        )
        self.assertEqual(click.response.sent[0][0], DENIED_TEXT)

    async def test_tidy_without_service_returns_empty_proposal(self):
        service = FakeService()
        group = create_memories_group(service, PermissionService(), FakeMaintenance())
        command = group.get_command('tidy')
        interaction = FakeInteraction(administrator=True)

        await command.callback(interaction)

        self.assertTrue(interaction.response.deferred[0]['ephemeral'])
        self.assertIn('整理案', interaction.edited_original[0]['content'])

    async def test_tidy_with_apply_button_closes_attention(self):
        action = CareMaintenanceAction('close_attention', ('care_0001',))
        maintenance = FakeMaintenance(CareMaintenanceProposal(1, (action,)))
        service = FakeService((mark('care_0001', 'attention', 'open', '一区切り'),))
        group = create_memories_group(service, PermissionService(), maintenance)
        command = group.get_command('tidy')
        interaction = FakeInteraction(administrator=True)

        await command.callback(interaction)
        view = interaction.edited_original[0]['view']
        click = FakeInteraction(administrator=True)
        await button(view, '閉じる').callback(click)

        self.assertIn(('apply_selected', 1, 'close_attention'), maintenance.calls)
        self.assertIn('閉じたよ', click.response.edits[0]['content'])

    async def test_tidy_button_rejects_non_admin(self):
        action = CareMaintenanceAction('close_attention', ('care_0001',))
        maintenance = FakeMaintenance(CareMaintenanceProposal(1, (action,)))
        service = FakeService((mark('care_0001', 'attention', 'open', '一区切り'),))
        group = create_memories_group(service, PermissionService(), maintenance)
        command = group.get_command('tidy')
        interaction = FakeInteraction(administrator=True)

        await command.callback(interaction)
        view = interaction.edited_original[0]['view']
        click = FakeInteraction(administrator=False)
        await button(view, '閉じる').callback(click)

        self.assertEqual(click.response.sent[0][0], DENIED_TEXT)
        self.assertEqual(maintenance.calls, [('propose_for_stream', 1)])
