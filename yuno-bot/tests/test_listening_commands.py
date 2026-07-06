from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import discord

from yuno.commands.listening import create_listening_group
from yuno.listening.models import ListeningChannel, ListeningChange


class FakeService:
    def __init__(
        self,
        *,
        items=(),
        add_result=None,
        remove_result=None,
        clear_count=0,
    ):
        self.items = list(items)
        self.add_result = add_result or ListeningChange(True, "db", "added")
        self.remove_result = remove_result
        self.clear_count = clear_count
        self.list_for_guild_calls = []
        self.add_calls = []
        self.remove_calls = []
        self.clear_calls = []

    async def list_all(self):
        raise AssertionError("/listening list should be scoped to the current guild")

    async def list_for_guild(self, guild_id):
        self.list_for_guild_calls.append(guild_id)
        return self.items

    async def add(self, channel_id, guild_id):
        self.add_calls.append((channel_id, guild_id))
        return self.add_result

    async def remove(self, channel_id):
        self.remove_calls.append(channel_id)
        return self.remove_result

    async def clear(self, guild_id):
        self.clear_calls.append(guild_id)
        return self.clear_count


class FakeResponse:
    def __init__(self):
        self.sent = []

    async def send_message(self, content, **kwargs):
        self.sent.append((content, kwargs))


class FakeInteraction:
    def __init__(self, *, guild_id=1, channel_ids=(10, 11)):
        self.guild_id = guild_id
        self.user = SimpleNamespace(
            guild_permissions=SimpleNamespace(manage_channels=True)
        )
        self.response = FakeResponse()

        if guild_id is None:
            self.guild = None
            self.channel = None
            return

        guild = SimpleNamespace(id=guild_id)
        channels = {}
        for channel_id in channel_ids:
            channel = Mock(spec=discord.TextChannel)
            channel.id = channel_id
            channel.guild = guild
            channels[channel_id] = channel
        guild.get_channel = lambda channel_id: channels.get(channel_id)

        self.guild = guild
        self.channel = channels[channel_ids[0]]


class ListeningCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_limits_to_current_guild_and_hides_source_labels(self):
        service = FakeService(items=(
            ListeningChannel("10", "1", "env"),
            ListeningChannel("11", "1", "db"),
            ListeningChannel("99", "2", "db"),
        ))
        command = create_listening_group(service).get_command("list")
        interaction = FakeInteraction()

        await command.callback(interaction)

        self.assertEqual(service.list_for_guild_calls, ["1"])
        text = interaction.response.sent[0][0]
        self.assertIn("<#10>", text)
        self.assertIn("<#11>", text)
        self.assertNotIn("<#99>", text)
        self.assertNotIn("最初から入っている場所", text)
        self.assertNotIn("後から追加した場所", text)
        self.assertNotIn(".env", text)
        self.assertNotIn("DB", text)

    async def test_list_denies_dm_without_reading_all_channels(self):
        service = FakeService(items=(ListeningChannel("10", "1", "db"),))
        command = create_listening_group(service).get_command("list")
        interaction = FakeInteraction(guild_id=None)

        await command.callback(interaction)

        self.assertEqual(interaction.response.sent[0][0], "サーバーで使って")
        self.assertEqual(service.list_for_guild_calls, [])

    async def test_add_and_remove_use_channel_wording(self):
        add_service = FakeService(add_result=ListeningChange(True, "db", "added"))
        add = create_listening_group(add_service).get_command("add")
        add_interaction = FakeInteraction()

        await add.callback(add_interaction, None)

        self.assertEqual(add_interaction.response.sent[0][0], "このチャンネルを聞くようにした")
        self.assertEqual(add_service.add_calls, [("10", "1")])

        existing_service = FakeService(
            add_result=ListeningChange(False, "db", "already_listening")
        )
        existing = create_listening_group(existing_service).get_command("add")
        existing_interaction = FakeInteraction()

        await existing.callback(existing_interaction, None)

        self.assertEqual(existing_interaction.response.sent[0][0], "このチャンネルはもう聞いている")

        missing_service = FakeService(
            remove_result=ListeningChange(False, None, "not_found")
        )
        remove = create_listening_group(missing_service).get_command("remove")
        remove_interaction = FakeInteraction()

        await remove.callback(remove_interaction, None)

        self.assertEqual(remove_interaction.response.sent[0][0], "このチャンネルは聞いていないよ")

    async def test_protected_remove_and_clear_hide_storage_terms(self):
        protected_service = FakeService(
            remove_result=ListeningChange(False, "env", "env_protected")
        )
        group = create_listening_group(protected_service)
        remove = group.get_command("remove")
        remove_interaction = FakeInteraction()

        await remove.callback(remove_interaction, None)

        remove_text = remove_interaction.response.sent[0][0]
        self.assertIn("固定設定", remove_text)
        self.assertIn("コマンドでは外せない", remove_text)
        self.assertNotIn(".env", remove_text)

        clear_service = FakeService(clear_count=2)
        clear = create_listening_group(clear_service).get_command("clear")
        clear_interaction = FakeInteraction()
        await clear.callback(clear_interaction)

        clear_text = clear_interaction.response.sent[0][0]
        self.assertEqual(clear_text, "聞く場所を2件外した")
        self.assertNotIn("DB", clear_text)

        empty_clear_service = FakeService(clear_count=0)
        empty_clear = create_listening_group(empty_clear_service).get_command("clear")
        empty_clear_interaction = FakeInteraction()
        await empty_clear.callback(empty_clear_interaction)

        self.assertEqual(empty_clear_interaction.response.sent[0][0], "外せる場所はなかった")


if __name__ == "__main__":
    unittest.main()
