from types import SimpleNamespace
import unittest

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
