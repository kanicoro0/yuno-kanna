import asyncio
from pathlib import Path
import tempfile
import unittest

from yuno.care_marks.repository import CareMarkRepository
from yuno.care_marks.service import CareMarkService
from yuno.commands.admin_service import CareMarkCommandService
from yuno.conversation.repository import ConversationRepository
from yuno.infra.database import Database


class SourceBoundMarkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / 'source-marks.db')
        await self.database.open()
        self.conversations = ConversationRepository(self.database)
        self.marks = CareMarkService(CareMarkRepository(self.database))
        self.service = CareMarkCommandService(
            self.conversations, self.marks
        )
        self.stream = await self.conversations.get_or_create_stream(
            'channel', '10', '1'
        )
        self.message = await self.conversations.append(
            self.stream.id,
            'message-1',
            'user',
            '7',
            'A',
            '同じ本文でもIDで結ぶ',
        )
        self.other_message = await self.conversations.append(
            self.stream.id,
            'message-2',
            'user',
            '7',
            'A',
            '同じ本文でもIDで結ぶ',
        )

    async def asyncTearDown(self):
        await self.database.close()
        self.temp_dir.cleanup()

    async def source_marks(self, message, kind):
        return await self.marks.list_for_source(
            self.stream.id, message.id, kind
        )

    async def test_repeated_save_reuses_memory_mark(self):
        first = await self.service.reuse_mark_from_message(
            '10', 'message-1', 'memory'
        )
        second = await self.service.reuse_mark_from_message(
            '10', 'message-1', 'memory'
        )

        self.assertEqual((first.outcome, second.outcome), ('created', 'existing'))
        marks = await self.source_marks(self.message, 'memory')
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0].status, 'draft')

    async def test_concurrent_save_still_creates_one_memory_mark(self):
        results = await asyncio.gather(*(
            self.service.reuse_mark_from_message(
                '10', 'message-1', 'memory'
            )
            for _ in range(4)
        ))

        self.assertEqual(
            [result.outcome for result in results].count('created'), 1
        )
        self.assertEqual(len(await self.source_marks(self.message, 'memory')), 1)

    async def test_hidden_memory_save_places_it_back_as_draft(self):
        first = await self.service.reuse_mark_from_message(
            '10', 'message-1', 'memory'
        )
        await self.marks.update(first.mark.public_id, status='hidden')

        result = await self.service.reuse_mark_from_message(
            '10', 'message-1', 'memory'
        )

        self.assertEqual(result.outcome, 'reopened')
        self.assertEqual(result.mark.status, 'draft')
        self.assertEqual(len(await self.source_marks(self.message, 'memory')), 1)

    async def test_active_memory_save_keeps_existing_active_mark(self):
        first = await self.service.reuse_mark_from_message(
            '10', 'message-1', 'memory'
        )
        await self.marks.update(first.mark.public_id, status='active')

        result = await self.service.reuse_mark_from_message(
            '10', 'message-1', 'memory'
        )

        self.assertEqual(result.outcome, 'existing')
        self.assertEqual(result.mark.status, 'active')
        self.assertEqual(len(await self.source_marks(self.message, 'memory')), 1)

    async def test_repeated_later_reuses_open_attention(self):
        first = await self.service.reuse_mark_from_message(
            '10', 'message-1', 'attention'
        )
        second = await self.service.reuse_mark_from_message(
            '10', 'message-1', 'attention'
        )

        self.assertEqual((first.outcome, second.outcome), ('created', 'existing'))
        self.assertEqual(len(await self.source_marks(self.message, 'attention')), 1)

    async def test_closed_and_hidden_attention_reopen(self):
        first = await self.service.reuse_mark_from_message(
            '10', 'message-1', 'attention'
        )
        for status in ('closed', 'hidden'):
            await self.marks.update(first.mark.public_id, status=status)

            result = await self.service.reuse_mark_from_message(
                '10', 'message-1', 'attention'
            )

            self.assertEqual(result.outcome, 'reopened')
            self.assertEqual(result.mark.status, 'open')
            first = result
        self.assertEqual(len(await self.source_marks(self.message, 'attention')), 1)

    async def test_close_targets_only_newest_matching_open_attention(self):
        older = await self.marks.create(
            self.stream.id,
            'attention',
            'open',
            'older',
            source_message_id=self.message.id,
        )
        newer = await self.marks.create(
            self.stream.id,
            'attention',
            'open',
            'newer',
            source_message_id=self.message.id,
        )
        unrelated = await self.marks.create(
            self.stream.id,
            'attention',
            'open',
            'unrelated',
            source_message_id=self.other_message.id,
        )

        result = await self.service.close_attention_from_message(
            '10', 'message-1'
        )

        self.assertEqual(result.mark.public_id, newer.public_id)
        selected = await self.source_marks(self.message, 'attention')
        self.assertEqual(
            [(mark.public_id, mark.status) for mark in selected],
            [(newer.public_id, 'closed'), (older.public_id, 'open')],
        )
        other = await self.source_marks(self.other_message, 'attention')
        self.assertEqual(
            [(mark.public_id, mark.status) for mark in other],
            [(unrelated.public_id, 'open')],
        )


if __name__ == '__main__':
    unittest.main()
