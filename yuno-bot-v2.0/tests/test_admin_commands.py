from pathlib import Path
import tempfile
import unittest

from yuno.attention.repository import AttentionRepository
from yuno.attention.service import AttentionService
from yuno.commands.admin_service import CoreAdminService
from yuno.conversation.context import ContextBuilder
from yuno.conversation.repository import ConversationRepository
from yuno.infra.database import Database
from yuno.interest.repository import InterestRepository
from yuno.interest.service import InterestService
from yuno.memory.repository import MemoryMarkRepository
from yuno.memory.service import MemoryMarkService


class AdminCommandServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "admin.sqlite3")
        await self.database.open()
        self.conversations = ConversationRepository(self.database)
        self.memory = MemoryMarkService(MemoryMarkRepository(self.database))
        self.attention = AttentionService(AttentionRepository(self.database))
        self.interest = InterestService(InterestRepository(self.database))
        self.admin = CoreAdminService(
            self.conversations, self.memory, self.attention, self.interest
        )

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    async def test_memory_manual_scope_filters_and_sensitive_downgrade(self) -> None:
        pending = await self.admin.add_memory("10", "1", "候補")
        active = await self.admin.add_memory("10", "1", "使える印", "active")
        sensitive = await self.admin.add_memory("10", "1", "通院のこと", "active")
        other = await self.admin.add_memory("20", "1", "別channel", "active")
        self.assertEqual(pending.provenance, "manual")
        self.assertEqual(sensitive.status, "pending")
        self.assertEqual(
            [item.public_id for item in await self.admin.list_memory("10", "1", "active", 10)],
            [active.public_id],
        )
        self.assertIsNone(await self.admin.set_memory_status("10", other.public_id, "hidden"))
        self.assertEqual(
            (await self.admin.set_memory_status("10", pending.public_id, "active")).status,
            "active",
        )
        self.assertEqual(
            (await self.admin.set_memory_status("10", pending.public_id, "hidden")).status,
            "hidden",
        )
        self.assertEqual(
            (await self.admin.set_memory_status("10", pending.public_id, "pending")).status,
            "pending",
        )

    async def test_attention_transitions_are_same_stream_only(self) -> None:
        item = await self.admin.add_attention("10", "1", "開いた話", 2.0)
        other = await self.admin.add_attention("20", "1", "別channel")
        self.assertEqual(item.rank, 1.0)
        self.assertIsNone(await self.admin.set_attention_status("10", other.public_id, "closed"))
        self.assertEqual(
            (await self.admin.set_attention_status("10", item.public_id, "closed")).status,
            "closed",
        )
        self.assertEqual(await self.admin.list_attention("10", "1", "open", 10), [])
        self.assertEqual(
            (await self.admin.set_attention_status("10", item.public_id, "hidden")).status,
            "hidden",
        )
        self.assertEqual(
            (await self.admin.set_attention_status("10", item.public_id, "open")).status,
            "open",
        )

    async def test_interest_sleep_hide_wake_and_context_exclusion(self) -> None:
        item = await self.admin.add_interest("10", "1", "星", 4.0)
        other = await self.admin.add_interest("20", "1", "別channel", 0.4)
        self.assertEqual(item.source, "manual")
        self.assertEqual(item.weight, 1.0)
        self.assertIsNone(await self.admin.set_interest_status("10", other.public_id, "hidden"))
        self.assertEqual(
            (await self.admin.set_interest_status("10", item.public_id, "sleeping")).status,
            "sleeping",
        )
        stream = await self.conversations.get_stream_by_channel_id("10")
        context = await ContextBuilder(
            self.conversations, self.memory, self.attention, self.interest
        ).build(stream.id)
        self.assertNotIn("星", {ref.content for ref in context.references})
        self.assertEqual(await self.interest.list_for_care(stream.id), [])
        self.assertEqual(
            (await self.admin.set_interest_status("10", item.public_id, "active")).status,
            "active",
        )
        self.assertEqual(
            (await self.admin.set_interest_status("10", item.public_id, "hidden")).status,
            "hidden",
        )
        self.assertEqual(await self.interest.references_for_stream(stream.id), [])

    async def test_dm_and_guild_channel_streams_do_not_mix(self) -> None:
        dm = await self.admin.add_memory("30", None, "DMの印", "active")
        guild = await self.admin.add_memory("10", "1", "guildの印", "active")
        self.assertEqual(
            [item.public_id for item in await self.admin.list_memory("30", None, "active", 10)],
            [dm.public_id],
        )
        self.assertEqual(
            [item.public_id for item in await self.admin.list_memory("10", "1", "active", 10)],
            [guild.public_id],
        )
