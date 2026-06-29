from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from yuno.commands.listening import _can_change
from yuno.config import Settings
from yuno.conversation.repository import ConversationRepository
from yuno.discord.routing import MessageRouter
from yuno.infra.database import Database
from yuno.listening.repository import ListeningChannelRepository
from yuno.listening.service import ListeningChannelService
from yuno.messages import IncomingMessage


class FakeResponse:
    def __init__(self):
        self.calls = []

    async def send_message(self, text, **kwargs):
        self.calls.append((text, kwargs))


class ListeningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "listening.sqlite3")
        await self.database.open()
        self.repository = ListeningChannelRepository(self.database)
        self.service = ListeningChannelService(self.repository, {10})

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    async def test_env_and_db_are_merged_and_only_db_can_be_removed(self) -> None:
        added = await self.service.add("20", "1")
        self.assertTrue(added.changed)
        self.assertTrue(await self.service.is_listening("10"))
        self.assertTrue(await self.service.is_listening("20"))
        self.assertEqual(
            {(item.discord_channel_id, item.source) for item in await self.service.list_all()},
            {("10", "env"), ("20", "db")},
        )
        protected = await self.service.remove("10")
        removed = await self.service.remove("20")
        self.assertEqual(protected.reason, "env_protected")
        self.assertTrue(removed.changed)
        self.assertFalse(await self.service.is_listening("20"))

    async def test_clear_removes_only_db_rows_for_guild(self) -> None:
        await self.service.add("20", "1")
        await self.service.add("30", "2")
        self.assertEqual(await self.service.clear("1"), 1)
        self.assertTrue(await self.service.is_listening("10"))
        self.assertFalse(await self.service.is_listening("20"))
        self.assertTrue(await self.service.is_listening("30"))

    async def test_db_change_affects_router_without_restart(self) -> None:
        conversations = ConversationRepository(self.database)
        settings = Settings("", None, "", "", Path("unused"), frozenset({10}),
                            ("ゆの", "唯乃", "yuno"), "INFO")
        router = MessageRouter(settings, conversations, self.service)
        message = IncomingMessage(
            "1", "20", "1", "channel", "7", "A", False, "99", False,
            "近くの通常発言", "now", None,
        )
        self.assertFalse((await router.route(message)).should_store)
        await self.service.add("20", "1")
        route = await router.route(message)
        self.assertTrue(route.should_store)
        self.assertFalse(route.should_reply)
        await self.service.remove("20")
        self.assertFalse((await router.route(message)).should_store)

    async def test_dm_and_missing_permissions_are_denied_ephemerally(self) -> None:
        for guild_id, allowed in ((None, True), (1, False)):
            response = FakeResponse()
            interaction = SimpleNamespace(
                guild_id=guild_id,
                user=SimpleNamespace(
                    guild_permissions=SimpleNamespace(manage_channels=allowed)
                ),
                response=response,
            )
            self.assertFalse(await _can_change(interaction))
            self.assertTrue(response.calls[0][1]["ephemeral"])
