from pathlib import Path
import tempfile
import unittest

from yuno.attention.repository import AttentionRepository
from yuno.attention.service import AttentionService
from yuno.care.models import InterestUpdate
from yuno.conversation.context import ContextBuilder
from yuno.conversation.repository import ConversationRepository
from yuno.infra.database import Database
from yuno.interest.repository import InterestRepository
from yuno.interest.service import InterestService
from yuno.memory.repository import MemoryMarkRepository
from yuno.memory.service import MemoryMarkService


class CoreReferenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "core.sqlite3")
        await self.database.open()
        self.conversations = ConversationRepository(self.database)
        self.memory = MemoryMarkService(MemoryMarkRepository(self.database))
        self.attention = AttentionService(AttentionRepository(self.database))
        self.interest = InterestService(InterestRepository(self.database))
        self.context = ContextBuilder(
            self.conversations, self.memory, self.attention, self.interest
        )
        self.stream = await self.conversations.get_or_create_stream("channel", "10", "1")
        self.other = await self.conversations.get_or_create_stream("channel", "20", "1")
        self.message = await self.conversations.append(
            self.stream.id, "m1", "user", "7", "A", "会話"
        )
        self.other_message = await self.conversations.append(
            self.other.id, "m2", "user", "8", "B", "別の会話"
        )

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    async def test_memory_states_ids_and_stream_scope(self) -> None:
        pending = await self.memory.create_pending_from_care(
            self.stream.id, self.message.id, "まだ候補"
        )
        active = await self.memory.create_pending_from_care(
            self.stream.id, self.message.id, "参照してよい", status="active"
        )
        await self.memory.create_pending_from_care(
            self.other.id, self.other_message.id, "別stream", status="active"
        )
        self.assertEqual(pending.public_id, "mem_0001")
        self.assertEqual(active.public_id, "mem_0002")
        self.assertEqual((await self.memory.activate(pending.public_id)).status, "active")
        self.assertEqual((await self.memory.hide(pending.public_id)).status, "hidden")
        self.assertEqual(
            (await self.memory.restore_to_pending(pending.public_id)).status, "pending"
        )
        references = await self.memory.references_for_stream(self.stream.id)
        self.assertEqual([item.content for item in references], ["参照してよい"])

    async def test_attention_touch_close_hide_and_scope(self) -> None:
        first = await self.attention.create_open(
            self.stream.id, "まだ開いている", self.message.id
        )
        second = await self.attention.create_open(
            self.stream.id, "隠すもの", self.message.id
        )
        await self.attention.create_open(
            self.other.id, "別stream", self.other_message.id
        )
        self.assertEqual(first.public_id, "att_0001")
        touched = await self.attention.touch_many(self.stream.id, (first.public_id,))
        self.assertEqual([item.public_id for item in touched], [first.public_id])
        self.assertEqual((await self.attention.close(first.public_id)).status, "closed")
        self.assertEqual((await self.attention.hide(second.public_id)).status, "hidden")
        self.assertEqual(await self.attention.references_for_stream(self.stream.id), [])

    async def test_interest_upsert_clamp_hide_and_scope(self) -> None:
        first = await self.interest.repository.upsert_term(
            self.stream.id, "星", 2.0, "manual"
        )
        updated = await self.interest.repository.upsert_term(
            self.stream.id, "星", -1.0, "manual"
        )
        normal = await self.interest.update_from_care(
            self.stream.id, (InterestUpdate("雨", 0.9),)
        )
        await self.interest.repository.upsert_term(
            self.other.id, "別stream", 0.4, "manual"
        )
        self.assertEqual(first.public_id, "int_0001")
        self.assertEqual(updated.public_id, first.public_id)
        self.assertEqual(updated.weight, 0.0)
        self.assertEqual(normal[0].weight, 0.6)
        await self.interest.hide(first.public_id)
        refs = await self.interest.references_for_stream(self.stream.id)
        self.assertEqual([item.term for item in refs], ["雨"])

    async def test_context_contains_only_visible_same_stream_references(self) -> None:
        active = await self.memory.create_pending_from_care(
            self.stream.id, self.message.id, "active memory", status="active"
        )
        hidden = await self.memory.create_pending_from_care(
            self.stream.id, self.message.id, "hidden memory", status="active"
        )
        await self.memory.hide(hidden.public_id)
        open_item = await self.attention.create_open(
            self.stream.id, "open attention", self.message.id
        )
        closed = await self.attention.create_open(
            self.stream.id, "closed attention", self.message.id
        )
        await self.attention.close(closed.public_id)
        interest = await self.interest.repository.upsert_term(
            self.stream.id, "interest", 0.4, "manual"
        )
        hidden_interest = await self.interest.repository.upsert_term(
            self.stream.id, "hidden interest", 0.4, "manual"
        )
        await self.interest.hide(hidden_interest.public_id)
        await self.memory.create_pending_from_care(
            self.other.id, self.other_message.id, "other memory", status="active"
        )

        context = await self.context.build(self.stream.id)
        contents = {item.content for item in context.references}
        self.assertEqual(contents, {"active memory", "open attention", "interest"})
        self.assertEqual(
            {item.public_id for item in context.references},
            {active.public_id, open_item.public_id, interest.public_id},
        )
        rendered = str(context)
        for forbidden in (
            "hidden memory", "closed attention", "hidden interest", "other memory",
            "reply_mode", "routing reason", "salience", "CareReader reason",
        ):
            self.assertNotIn(forbidden, rendered)
