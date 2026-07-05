from types import SimpleNamespace
import unittest

import discord

from yuno.commands.status import (
    LISTEN_LABEL,
    REFRESH_LABEL,
    REMOVE_LABEL,
    create_status_command,
    status_text,
)
from yuno.discord.ui import DENIED_TEXT, STALE_TEXT
from yuno.listening.models import ListeningChange, ListeningChannel
from yuno.permissions import PermissionService


class FakeListening:
    def __init__(self, items=()):
        self.items = list(items)
        self.calls = []

    async def list_all(self):
        self.calls.append(('list_all',))
        return list(self.items)

    async def add(self, channel_id, guild_id):
        self.calls.append(('add', channel_id, guild_id))
        if not any(item.discord_channel_id == channel_id for item in self.items):
            self.items.append(ListeningChannel(channel_id, guild_id, 'db'))
            return ListeningChange(True, 'db', 'added')
        return ListeningChange(False, 'db', 'already_listening')

    async def remove(self, channel_id):
        self.calls.append(('remove', channel_id))
        before = len(self.items)
        self.items = [
            item for item in self.items
            if item.discord_channel_id != channel_id
        ]
        return ListeningChange(
            len(self.items) != before,
            'db',
            'removed' if len(self.items) != before else 'not_found',
        )


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
    def __init__(
        self,
        user_id=7,
        *,
        guild_id=1,
        channel_id=10,
        administrator=False,
        text_channel=True,
    ):
        self.user = SimpleNamespace(
            id=user_id,
            guild_permissions=SimpleNamespace(administrator=administrator),
        )
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.channel = SimpleNamespace(
            type=(discord.ChannelType.text if text_channel else discord.ChannelType.voice)
        )
        self.response = FakeResponse()
        self.original_edits = []

    async def edit_original_response(self, **kwargs):
        self.original_edits.append(kwargs)


def button(view, label):
    return next(item for item in view.children if item.label == label)


class StatusTextTests(unittest.TestCase):
    def test_panel_contains_only_user_facing_information(self):
        text = status_text(
            (ListeningChannel('10', '1', 'db'),),
            ('ゆの', '唯乃'),
            '10',
            True,
        )

        self.assertIn('この場所: 聞いてる', text)
        self.assertIn('変更: できる', text)
        self.assertIn('ゆの、唯乃', text)
        for internal in ('CareMark', 'ReadCue', 'reply_mode', '.env', 'DB', 'db'):
            self.assertNotIn(internal, text)

    def test_empty_list_renders_naturally(self):
        text = status_text((), ('ゆの',))

        self.assertIn('聞き耳の場所: まだない', text)

    def test_no_channel_context_does_not_list_other_channel_ids(self):
        text = status_text(
            (ListeningChannel('987654', '1', 'db'),), ('ゆの',)
        )

        self.assertIn('聞き耳の場所: 設定されている', text)
        self.assertNotIn('987654', text)

    def test_fixed_place_uses_natural_wording(self):
        text = status_text(
            (ListeningChannel('10', None, 'env'),),
            ('ゆの',),
            '10',
            True,
        )

        self.assertIn('最初から入っている場所', text)
        self.assertNotIn('.env', text)


class StatusCommandTests(unittest.IsolatedAsyncioTestCase):
    async def open_panel(self, listening, interaction, owner_ids=()):
        command = create_status_command(
            listening,
            ('ゆの',),
            PermissionService(owner_ids),
        )
        await command.callback(interaction)
        return interaction.response.sent[0][1]['view']

    async def test_status_returns_ephemeral_panel_with_current_action(self):
        interaction = FakeInteraction(administrator=True)
        view = await self.open_panel(FakeListening(), interaction)

        text, kwargs = interaction.response.sent[0]
        self.assertTrue(kwargs['ephemeral'])
        self.assertIs(kwargs['view'], view)
        self.assertIn(LISTEN_LABEL, [item.label for item in view.children])
        self.assertIn(REFRESH_LABEL, [item.label for item in view.children])
        self.assertIn('この場所: ここでは聞いてない', text)

    async def test_non_text_context_has_only_refresh(self):
        interaction = FakeInteraction(text_channel=False)
        view = await self.open_panel(FakeListening(), interaction)

        self.assertEqual([item.label for item in view.children], [REFRESH_LABEL])

    async def test_fixed_place_has_no_remove_button(self):
        listening = FakeListening((ListeningChannel('10', None, 'env'),))
        interaction = FakeInteraction(administrator=True)
        view = await self.open_panel(listening, interaction)

        self.assertEqual([item.label for item in view.children], [REFRESH_LABEL])

    async def test_denied_change_is_ephemeral_and_does_not_mutate(self):
        listening = FakeListening()
        opening = FakeInteraction(administrator=False)
        view = await self.open_panel(listening, opening)
        click = FakeInteraction(administrator=False)

        await button(view, LISTEN_LABEL).callback(click)

        self.assertNotIn('add', [call[0] for call in listening.calls])
        self.assertEqual(click.response.sent[0][0], DENIED_TEXT)
        self.assertTrue(click.response.sent[0][1]['ephemeral'])

    async def test_change_uses_listening_service_then_edits_panel(self):
        listening = FakeListening()
        opening = FakeInteraction(administrator=True)
        view = await self.open_panel(listening, opening)
        click = FakeInteraction(administrator=True)

        await button(view, LISTEN_LABEL).callback(click)

        self.assertIn(('add', '10', '1'), listening.calls)
        self.assertEqual(click.response.sent, [])
        self.assertIn('この場所: 聞いてる', click.response.edits[0]['content'])
        self.assertIn(
            REMOVE_LABEL,
            [item.label for item in click.response.edits[0]['view'].children],
        )

    async def test_refresh_updates_panel_without_new_message(self):
        listening = FakeListening()
        opening = FakeInteraction(administrator=True)
        view = await self.open_panel(listening, opening)
        listening.items.append(ListeningChannel('10', '1', 'db'))
        click = FakeInteraction(administrator=True)

        await button(view, REFRESH_LABEL).callback(click)

        self.assertEqual(click.response.sent, [])
        self.assertEqual(len(click.response.edits), 1)
        self.assertIn('この場所: 聞いてる', click.response.edits[0]['content'])

    async def test_remove_uses_existing_listening_service_path(self):
        listening = FakeListening((ListeningChannel('10', '1', 'db'),))
        opening = FakeInteraction(administrator=True)
        view = await self.open_panel(listening, opening)
        click = FakeInteraction(administrator=True)

        await button(view, REMOVE_LABEL).callback(click)

        self.assertIn(('remove', '10'), listening.calls)
        self.assertIn(
            'この場所: ここでは聞いてない',
            click.response.edits[0]['content'],
        )

    async def test_stale_status_button_is_rejected_safely(self):
        opening = FakeInteraction(administrator=True)
        view = await self.open_panel(FakeListening(), opening)
        await view.on_timeout()
        click = FakeInteraction(user_id=opening.user.id, administrator=True)

        allowed = await view.interaction_check(click)

        self.assertFalse(allowed)
        self.assertEqual(click.response.sent[0][0], STALE_TEXT)


if __name__ == '__main__':
    unittest.main()
