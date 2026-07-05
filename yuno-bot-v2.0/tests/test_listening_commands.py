from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import discord

from yuno.commands.listening import create_listening_group
from yuno.listening.models import ListeningChannel, ListeningChange


class FakeService:
    def __init__(self, *, items=(), remove_result=None, clear_count=0):
        self.items = list(items)
        self.remove_result = remove_result
        self.clear_count = clear_count

    async def list_all(self):
        return self.items

    async def remove(self, channel_id):
        return self.remove_result

    async def clear(self, guild_id):
        return self.clear_count


class FakeResponse:
    def __init__(self):
        self.sent = []

    async def send_message(self, content, **kwargs):
        self.sent.append((content, kwargs))


class FakeInteraction:
    def __init__(self):
        channel = Mock(spec=discord.TextChannel)
        channel.id = 10
        channel.guild = SimpleNamespace(id=1)
        self.guild_id = 1
        self.channel = channel
        self.user = SimpleNamespace(
            guild_permissions=SimpleNamespace(manage_channels=True)
        )
        self.response = FakeResponse()


class ListeningCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_uses_user_facing_source_labels(self):
        service = FakeService(items=(
            ListeningChannel('10', '1', 'env'),
            ListeningChannel('11', '1', 'database'),
        ))
        command = create_listening_group(service).get_command('list')
        interaction = FakeInteraction()

        await command.callback(interaction)

        text = interaction.response.sent[0][0]
        self.assertIn('最初から入っている場所', text)
        self.assertIn('後から追加した場所', text)
        self.assertNotIn('.env', text)
        self.assertNotIn('DB', text)

    async def test_protected_remove_and_clear_hide_storage_terms(self):
        protected_service = FakeService(
            remove_result=ListeningChange(False, 'env', 'env_protected')
        )
        group = create_listening_group(protected_service)
        remove = group.get_command('remove')
        remove_interaction = FakeInteraction()

        await remove.callback(remove_interaction, None)

        remove_text = remove_interaction.response.sent[0][0]
        self.assertIn('コマンドでは外せない', remove_text)
        self.assertNotIn('.env', remove_text)

        clear_service = FakeService(clear_count=2)
        clear = create_listening_group(clear_service).get_command('clear')
        clear_interaction = FakeInteraction()
        await clear.callback(clear_interaction)

        clear_text = clear_interaction.response.sent[0][0]
        self.assertEqual(clear_text, '後から追加した場所を2件外した')
        self.assertNotIn('DB', clear_text)


if __name__ == '__main__':
    unittest.main()
