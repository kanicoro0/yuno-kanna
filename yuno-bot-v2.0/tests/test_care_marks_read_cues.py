from pathlib import Path
import tempfile
import unittest

from yuno.care_marks.repository import CareMarkRepository
from yuno.care_marks.service import CareMarkService
from yuno.conversation.repository import ConversationRepository
from yuno.infra.database import Database
from yuno.read_cues.repository import ReadCueRepository
from yuno.read_cues.service import ReadCueService


class CareMarkReadCueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / 'care.sqlite3')
        await self.database.open()
        conversations = ConversationRepository(self.database)
        self.stream = await conversations.get_or_create_stream(
            'channel', '10', '1'
        )
        self.message = await conversations.append(
            self.stream.id, 'message-1', 'user', '7', 'A', 'conversation'
        )
        self.marks = CareMarkService(CareMarkRepository(self.database))
        self.cues = ReadCueService(ReadCueRepository(self.database))

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    async def test_care_mark_basic_crud_and_status_validation(self) -> None:
        mark = await self.marks.create(
            self.stream.id,
            'memory',
            'draft',
            '  remembered text  ',
            self.message.id,
        )
        self.assertEqual(mark.public_id, 'care_0001')
        self.assertEqual(mark.text, 'remembered text')
        self.assertEqual(
            (await self.marks.get_by_public_id(mark.public_id)).id, mark.id
        )

        updated = await self.marks.update(
            mark.public_id, status='active', text='updated text'
        )
        self.assertEqual((updated.status, updated.text), ('active', 'updated text'))
        touched = await self.marks.touch(mark.public_id)
        self.assertIsNotNone(touched.last_touched_at)
        self.assertEqual(
            [item.public_id for item in await self.marks.list_for_stream(
                self.stream.id, ('memory',), ('active',)
            )],
            [mark.public_id],
        )

        with self.assertRaises(ValueError):
            await self.marks.update(mark.public_id, status='open')
        self.assertTrue(await self.marks.delete(mark.public_id))
        self.assertIsNone(await self.marks.get_by_public_id(mark.public_id))

    async def test_attention_statuses_remain_distinct(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'attention', 'open', 'unfinished topic'
        )
        self.assertEqual(
            (await self.marks.update(mark.public_id, status='closed')).status,
            'closed',
        )
        with self.assertRaises(ValueError):
            await self.marks.update(mark.public_id, status='active')

    async def test_read_cue_upserts_by_mark_and_normalized_term(self) -> None:
        first_mark = await self.marks.create(
            self.stream.id, 'attention', 'open', 'first topic'
        )
        second_mark = await self.marks.create(
            self.stream.id, 'attention', 'open', 'second topic'
        )
        first = await self.cues.upsert(first_mark.id, ' Ｓｔａｒ ', 0.2)
        updated = await self.cues.upsert(
            first_mark.id, 'star', 0.8, 'sleeping'
        )
        separate = await self.cues.upsert(second_mark.id, 'star', 0.4)

        self.assertEqual(updated.id, first.id)
        self.assertEqual(updated.normalized_term, 'star')
        self.assertEqual((updated.weight, updated.status), (0.8, 'sleeping'))
        self.assertNotEqual(separate.id, first.id)
        self.assertEqual(
            [item.id for item in await self.cues.list_for_mark(
                first_mark.id, ('sleeping',)
            )],
            [first.id],
        )

        active = await self.cues.set_status(first.id, 'active')
        self.assertEqual(active.status, 'active')
        self.assertTrue(await self.cues.delete(first.id))
        self.assertIsNone(await self.cues.get(first.id))

    async def test_deleting_mark_cascades_to_read_cues(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'memory', 'active', 'marked text'
        )
        cue = await self.cues.upsert(mark.id, 'marked', 0.5)

        await self.marks.delete(mark.public_id)

        self.assertIsNone(await self.cues.get(cue.id))
