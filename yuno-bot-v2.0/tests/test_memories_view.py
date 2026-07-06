from types import SimpleNamespace
import unittest

from yuno.care.maintenance import (
    CareMaintenanceAction,
    CareMaintenanceProposal,
)
from yuno.care_marks.models import CareMark
from yuno.commands.core import (
    CLOSE_LABEL,
    HIDE_LABEL,
    MISSING_MARK_TEXT,
    RESTORE_LABEL,
    MemoriesView,
    action_for_mark,
    create_memories_group,
    render_care_marks,
    render_maintenance_proposal,
)
from yuno.discord.ui import DENIED_TEXT, STALE_TEXT
from yuno.permissions import PermissionService


def mark(public_id, kind, status, text='残している言葉'):
    return CareMark(
        id=int(public_id.split('_')[-1]),
        public_id=public_id,
        stream_id=1,
        source_message_id=None,
        kind=kind,
        status=status,
        text=text,
        created_at='now',
        updated_at='now',
    )


class FakeService:
    def __init__(self, marks=()):
        self.marks = list(marks)
        self.calls = []
        self.missing = False

    async def stream(self, channel_id, guild_id, create=False):
        self.calls.append(('stream', channel_id, guild_id, create))
        return SimpleNamespace(id=1)

    async def list_marks(self, channel_id, guild_id, kind, status, limit):
        self.calls.append(('list_marks', channel_id, guild_id, kind, status, limit))
        selected = list(self.marks)
        if kind != 'all':
            selected = [item for item in selected if item.kind == kind]
        if status == 'visible':
            selected = [
                item for item in selected if item.status in ('active', 'open')
            ]
        elif status != 'all':
            selected = [item for item in selected if item.status == status]
        return selected[:limit]

    async def set_status(self, channel_id, public_id, status):
        self.calls.append(('set_status', channel_id, public_id, status))
        if self.missing:
            return None
        for index, item in enumerate(self.marks):
            if item.public_id == public_id:
                updated = mark(item.public_id, item.kind, status, item.text)
                self.marks[index] = updated
                return updated
        return None


class FakeMaintenance:
    def __init__(self, proposal):
        self.proposal = proposal
        self.calls = []

    async def propose_for_stream(self, stream_id):
        self.calls.append(stream_id)
        return self.proposal


class FakeResponse:
    def __init__(self):
        self.sent = []
        self.edits = []
        self.done = False

    def is_done(self):
        return self.done

    async def send_message(self, content, **kwargs):
        self.sent.append((content, kwargs))
        self.done = True

    async def edit_message(self, **kwargs):
        self.edits.append(kwargs)
        self.done = True


class FakeInteraction:
    def __init__(self, user_id=7, *, administrator=False):
        self.user = SimpleNamespace(
            id=user_id,
            guild_permissions=SimpleNamespace(administrator=administrator),
        )
        self.guild_id = 1
        self.channel_id = 10
        self.response = FakeResponse()
        self.original_edits = []

    async def edit_original_response(self, **kwargs):
        self.original_edits.append(kwargs)


def button(view, suffix):
    return next(item for item in view.children if item.label.endswith(suffix))


class MemoriesViewTests(unittest.IsolatedAsyncioTestCase):
    async def open_list(self, service, interaction, **options):
        group = create_memories_group(service, PermissionService())
        command = group.get_command('list')
        await command.callback(
            interaction,
            options.get('kind', 'all'),
            options.get('status', 'visible'),
            options.get('limit', 10),
        )
        return interaction.response.sent[0][1].get('view')

    def test_renderer_uses_natural_rows_without_internal_words(self):
        text = render_care_marks((
            mark('care_0001', 'memory', 'active', '青い花'),
            mark('care_0002', 'attention', 'open', '続きの話'),
        ))

        self.assertIn('1. 覚えている', text)
        self.assertIn('2. まだ開いている', text)
        for internal in (
            'CareMark', 'ReadCue', 'memory', 'attention', 'active',
            'open', 'care_0001',
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
            CareMaintenanceAction('keep', ('care_0005',)),
        ))

        text = render_maintenance_proposal(proposal)

        for visible in (
            '整理案',
            '閉じてもよさそう',
            'まとめられそう',
            '短くしてもよさそう',
            'そのままでよさそう',
        ):
            self.assertIn(visible, text)
        for internal in (
            'CareMark', 'ReadCue', 'care_0001', 'public_id', 'source_id',
            'memory', 'attention', 'active', 'open', 'service', 'LLM',
        ):
            self.assertNotIn(internal, text)

    async def test_tidy_returns_ephemeral_proposals_without_mutation_buttons(self):
        marks = [mark('care_0001', 'attention', 'open', '軽い質問')]
        service = FakeService(marks)
        proposal = CareMaintenanceProposal(1, (
            CareMaintenanceAction('close_attention', ('care_0001',)),
        ))
        maintenance = FakeMaintenance(proposal)
        group = create_memories_group(
            service, PermissionService(), maintenance
        )
        interaction = FakeInteraction(administrator=True)

        await group.get_command('tidy').callback(interaction)

        text, kwargs = interaction.response.sent[0]
        self.assertTrue(kwargs['ephemeral'])
        self.assertNotIn('view', kwargs)
        self.assertIn('閉じてもよさそう', text)
        self.assertIn('軽い質問', text)
        self.assertNotIn('care_0001', text)
        self.assertEqual(maintenance.calls, [1])
        self.assertNotIn('set_status', [call[0] for call in service.calls])
        self.assertEqual(service.marks, marks)

    async def test_non_admin_tidy_cannot_see_or_generate_proposals(self):
        service = FakeService()
        maintenance = FakeMaintenance(CareMaintenanceProposal(1))
        group = create_memories_group(
            service, PermissionService(), maintenance
        )
        interaction = FakeInteraction(administrator=False)

        await group.get_command('tidy').callback(interaction)

        self.assertEqual(interaction.response.sent[0][0], DENIED_TEXT)
        self.assertEqual(service.calls, [])
        self.assertEqual(maintenance.calls, [])

    def test_button_action_mapping_is_stable(self):
        self.assertEqual(
            action_for_mark(mark('care_0001', 'memory', 'active')).label,
            HIDE_LABEL,
        )
        self.assertEqual(
            action_for_mark(mark('care_0002', 'attention', 'open')).label,
            CLOSE_LABEL,
        )
        self.assertEqual(
            action_for_mark(mark('care_0003', 'attention', 'closed')).label,
            RESTORE_LABEL,
        )
        self.assertIsNone(
            action_for_mark(mark('care_0005', 'memory', 'hidden'))
        )
        self.assertIsNone(
            action_for_mark(mark('care_0006', 'attention', 'hidden'))
        )
        self.assertIsNone(
            action_for_mark(mark('care_0004', 'memory', 'draft'))
        )

    def test_list_options_have_user_facing_help_and_choices(self):
        group = create_memories_group(FakeService(), PermissionService())
        command = group.get_command('list')
        parameters = {item.name: item for item in command.parameters}

        self.assertEqual(parameters['kind'].description, '見るものの種類')
        self.assertEqual(
            [choice.name for choice in parameters['kind'].choices],
            ['ぜんぶ', '残したもの', 'あとで見るもの'],
        )
        self.assertEqual(parameters['status'].description, 'いまの状態で絞る')
        self.assertIn(
            'いま見るもの',
            [choice.name for choice in parameters['status'].choices],
        )
        self.assertEqual(
            parameters['limit'].description,
            '表示する件数（1〜20）',
        )

    async def test_invalid_list_filters_give_short_user_facing_guidance(self):
        service = FakeService()
        group = create_memories_group(service, PermissionService())
        command = group.get_command('list')

        invalid_kind = FakeInteraction(administrator=True)
        await command.callback(invalid_kind, 'unknown', 'visible', 10)
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

    async def test_list_returns_ephemeral_panel_with_mark_buttons(self):
        service = FakeService((
            mark('care_0001', 'memory', 'active'),
            mark('care_0002', 'attention', 'open'),
        ))
        interaction = FakeInteraction(administrator=True)

        view = await self.open_list(service, interaction)

        text, kwargs = interaction.response.sent[0]
        self.assertTrue(kwargs['ephemeral'])
        self.assertIs(kwargs['view'], view)
        self.assertEqual(
            [item.label for item in view.children],
            [f'1 {HIDE_LABEL}', f'2 {CLOSE_LABEL}'],
        )
        self.assertNotIn('care_0001', text)

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

    async def test_direct_non_admin_button_use_does_not_mutate(self):
        service = FakeService((mark('care_0001', 'memory', 'active'),))
        view = MemoriesView(
            service,
            PermissionService(),
            opened_by_user_id=7,
            channel_id='10',
            guild_id='1',
            kind='all',
            status='visible',
            limit=10,
        )
        await view.prepare()
        click = FakeInteraction(administrator=False)

        await button(view, HIDE_LABEL).callback(click)

        self.assertNotIn('set_status', [call[0] for call in service.calls])
        self.assertEqual(click.response.sent[0][0], DENIED_TEXT)

    async def test_missing_mark_gives_short_safe_response(self):
        service = FakeService((mark('care_0001', 'memory', 'active'),))
        opening = FakeInteraction(administrator=True)
        view = await self.open_list(service, opening)
        service.missing = True
        click = FakeInteraction(administrator=True)

        await button(view, HIDE_LABEL).callback(click)

        self.assertEqual(click.response.sent[0][0], MISSING_MARK_TEXT)
        self.assertEqual(click.response.edits, [])

    async def test_stale_panel_rejects_interaction_safely(self):
        service = FakeService((mark('care_0001', 'memory', 'active'),))
        opening = FakeInteraction(administrator=True)
        view = await self.open_list(service, opening)
        await view.on_timeout()
        click = FakeInteraction(user_id=opening.user.id, administrator=True)

        allowed = await view.interaction_check(click)

        self.assertFalse(allowed)
        self.assertEqual(click.response.sent[0][0], STALE_TEXT)


if __name__ == '__main__':
    unittest.main()
