from types import SimpleNamespace
import unittest

import discord

from yuno.commands.message_actions import (
    CONTEXT_COMMAND_NAME,
    LATER_LABEL,
    MISSING_TARGET_TEXT,
    SAVE_LABEL,
    SelectedMessageView,
    create_selected_message_command,
    selected_message_text,
)
from yuno.discord.ui import DENIED_TEXT, STALE_TEXT
from yuno.permissions import PermissionService


class FakeChannel:
    def __init__(self, channel_id=10):
        self.id = channel_id
        self.available = True
        self.fetches = []

    async def fetch_message(self, message_id):
        self.fetches.append(message_id)
        if not self.available:
            raise discord.NotFound(SimpleNamespace(status=404, reason='gone'), 'gone')
        return SimpleNamespace(id=message_id)


class FakeMessage:
    def __init__(self, message_id=100, content='選んだ言葉', channel=None):
        self.id = message_id
        self.content = content
        self.channel = channel or FakeChannel()


class FakeService:
    def __init__(self):
        self.calls = []
        self.missing = False

    async def add_mark_from_message(self, channel_id, message_id, kind):
        self.calls.append((channel_id, message_id, kind))
        if self.missing:
            return None
        return SimpleNamespace(kind=kind)


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
        self.response = FakeResponse()
        self.original_edits = []

    async def edit_original_response(self, **kwargs):
        self.original_edits.append(kwargs)


def button(view, label):
    return next(item for item in view.children if item.label == label)


class SelectedMessageActionTests(unittest.IsolatedAsyncioTestCase):
    def test_context_command_is_global_message_command(self):
        command = create_selected_message_command(
            FakeService(), PermissionService()
        )

        self.assertEqual(command.name, CONTEXT_COMMAND_NAME)
        self.assertEqual(command.type, discord.AppCommandType.message)
        self.assertIsNone(command._guild_ids)
        self.assertFalse(command.guild_only)

    def test_panel_text_contains_no_internal_names(self):
        text = selected_message_text('短い本文')

        self.assertIn('選んだメッセージ', text)
        self.assertIn('短い本文', text)
        for internal in (
            'CareMark', 'ReadCue', 'DB', 'source_message_id',
            'memory', 'attention', 'draft', 'open',
        ):
            self.assertNotIn(internal, text)

    async def test_authorized_command_opens_ephemeral_panel(self):
        service = FakeService()
        command = create_selected_message_command(
            service, PermissionService()
        )
        interaction = FakeInteraction(administrator=True)

        await command.callback(interaction, FakeMessage())

        text, kwargs = interaction.response.sent[0]
        self.assertTrue(kwargs['ephemeral'])
        self.assertIn('選んだメッセージ', text)
        self.assertEqual(
            [item.label for item in kwargs['view'].children],
            [SAVE_LABEL, LATER_LABEL],
        )

    async def test_unauthorized_command_does_not_open_or_mutate(self):
        service = FakeService()
        command = create_selected_message_command(
            service, PermissionService()
        )
        interaction = FakeInteraction(administrator=False)

        await command.callback(interaction, FakeMessage())

        self.assertEqual(service.calls, [])
        self.assertEqual(interaction.response.sent[0][0], DENIED_TEXT)
        self.assertNotIn('view', interaction.response.sent[0][1])

    async def test_actions_only_use_selected_message_and_existing_service(self):
        service = FakeService()
        target = FakeMessage(message_id=222, channel=FakeChannel(33))
        view = SelectedMessageView(
            service,
            PermissionService(),
            target,
            opened_by_user_id=7,
        )
        click = FakeInteraction(administrator=True)

        await button(view, SAVE_LABEL).callback(click)

        self.assertEqual(service.calls, [('33', '222', 'memory')])
        self.assertEqual(target.channel.fetches, [222])
        self.assertEqual(click.response.sent, [])
        self.assertIn('残したよ', click.response.edits[0]['content'])

    async def test_later_action_uses_attention_path(self):
        service = FakeService()
        target = FakeMessage()
        view = SelectedMessageView(
            service,
            PermissionService(),
            target,
            opened_by_user_id=7,
        )
        click = FakeInteraction(administrator=True)

        await button(view, LATER_LABEL).callback(click)

        self.assertEqual(service.calls, [('10', '100', 'attention')])

    async def test_direct_unauthorized_button_use_does_not_mutate(self):
        service = FakeService()
        view = SelectedMessageView(
            service,
            PermissionService(),
            FakeMessage(),
            opened_by_user_id=7,
        )
        click = FakeInteraction(administrator=False)

        await button(view, SAVE_LABEL).callback(click)

        self.assertEqual(service.calls, [])
        self.assertEqual(click.response.sent[0][0], DENIED_TEXT)

    async def test_deleted_target_fails_safely(self):
        service = FakeService()
        target = FakeMessage()
        target.channel.available = False
        view = SelectedMessageView(
            service,
            PermissionService(),
            target,
            opened_by_user_id=7,
        )
        click = FakeInteraction(administrator=True)

        await button(view, SAVE_LABEL).callback(click)

        self.assertEqual(service.calls, [])
        self.assertEqual(click.response.sent[0][0], MISSING_TARGET_TEXT)

    async def test_unstored_target_fails_safely(self):
        service = FakeService()
        service.missing = True
        view = SelectedMessageView(
            service,
            PermissionService(),
            FakeMessage(),
            opened_by_user_id=7,
        )
        click = FakeInteraction(administrator=True)

        await button(view, SAVE_LABEL).callback(click)

        self.assertEqual(click.response.sent[0][0], MISSING_TARGET_TEXT)
        self.assertEqual(click.response.edits, [])

    async def test_stale_panel_rejects_interaction_safely(self):
        view = SelectedMessageView(
            FakeService(),
            PermissionService(),
            FakeMessage(),
            opened_by_user_id=7,
        )
        await view.on_timeout()
        click = FakeInteraction(administrator=True)

        allowed = await view.interaction_check(click)

        self.assertFalse(allowed)
        self.assertEqual(click.response.sent[0][0], STALE_TEXT)


if __name__ == '__main__':
    unittest.main()
