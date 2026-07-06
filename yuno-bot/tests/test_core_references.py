from pathlib import Path
import tempfile
import unittest

from yuno.care_marks.repository import CareMarkRepository
from yuno.care_marks.service import CareMarkService
from yuno.config import Settings
from yuno.conversation.context import ContextBuilder, REFERENCE_LIMIT
from yuno.conversation.reference_selector import ReferenceSelector
from yuno.conversation.repository import ConversationRepository
from yuno.discord.routing import MessageRouter
from yuno.infra.database import Database
from yuno.messages import IncomingMessage
from yuno.pipeline import ConversationPipeline
from yuno.read_cues.repository import ReadCueRepository
from yuno.read_cues.service import ReadCueService


class CoreReferenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / 'references.sqlite3')
        await self.database.open()
        self.conversations = ConversationRepository(self.database)
        self.marks = CareMarkService(CareMarkRepository(self.database))
        self.cues = ReadCueService(ReadCueRepository(self.database))
        self.context = ContextBuilder(self.conversations, self.marks)
        self.selector = ReferenceSelector(self.marks, self.cues)
        self.stream = await self.conversations.get_or_create_stream(
            'channel', '10', '1'
        )
        self.other_stream = await self.conversations.get_or_create_stream(
            'channel', '20', '1'
        )
        self.message = await self.conversations.append(
            self.stream.id, 'message-1', 'user', '7', 'A', '近くの会話'
        )

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    async def test_active_memory_and_open_attention_can_be_selected(self) -> None:
        memory = await self.marks.create(
            self.stream.id,
            'memory',
            'active',
            '星の記録を残した',
            self.message.id,
        )
        attention = await self.marks.create(
            self.stream.id,
            'attention',
            'open',
            '雨の日の散歩について',
            self.message.id,
        )

        memory_selection = await self.selector.select(
            self.stream.id, '星の記録を思い出した'
        )
        attention_selection = await self.selector.select(
            self.stream.id, '雨の日の散歩について話す'
        )

        self.assertIn(memory.public_id, memory_selection.care_mark_ids)
        self.assertIn(attention.public_id, attention_selection.care_mark_ids)

    async def test_hidden_closed_and_other_stream_marks_are_not_selected(self) -> None:
        hidden = await self.marks.create(
            self.stream.id, 'memory', 'hidden', '星の秘密'
        )
        closed = await self.marks.create(
            self.stream.id, 'attention', 'closed', '星の閉じた話'
        )
        other = await self.marks.create(
            self.other_stream.id, 'memory', 'active', '星の別stream'
        )

        selection = await self.selector.select(
            self.stream.id, '星の秘密と閉じた話'
        )
        context = await self.context.build(
            self.stream.id,
            (hidden.public_id, closed.public_id, other.public_id),
        )

        self.assertEqual(selection.care_mark_ids, ())
        self.assertEqual(context.references, ())

    async def test_read_cue_selects_mark_but_is_not_rendered(self) -> None:
        mark = await self.marks.create(
            self.stream.id,
            'attention',
            'open',
            'あの続きについて',
            self.message.id,
        )
        await self.cues.upsert(mark.id, '天体観測', 0.5)

        selection = await self.selector.select(
            self.stream.id, '天体観測はどうなったかな'
        )
        context = await self.context.build(
            self.stream.id, selection.care_mark_ids
        )

        self.assertEqual(selection.care_mark_ids, (mark.public_id,))
        self.assertEqual(len(context.references), 1)
        self.assertEqual(context.references[0].kind, 'attention')
        self.assertEqual(context.references[0].content, 'あの続きについて')
        self.assertNotIn('天体観測', str(context.references))
        self.assertNotIn('0.5', str(context.references))

    async def test_reference_limit_is_respected(self) -> None:
        marks = []
        for index in range(REFERENCE_LIMIT + 2):
            mark = await self.marks.create(
                self.stream.id,
                'memory',
                'active',
                f'参照断片 {index}',
                self.message.id,
            )
            await self.cues.upsert(mark.id, '共通cue', 0.5)
            marks.append(mark)

        selection = await self.selector.select(
            self.stream.id, '共通cueに触れた'
        )
        context = await self.context.build(
            self.stream.id, selection.care_mark_ids
        )

        self.assertEqual(len(selection.care_mark_ids), REFERENCE_LIMIT)
        self.assertEqual(len(context.references), REFERENCE_LIMIT)
        self.assertTrue(
            set(selection.care_mark_ids).issubset({
                mark.public_id for mark in marks
            })
        )

    async def test_directed_message_speaks_with_care_mark_context(self) -> None:
        mark = await self.marks.create(
            self.stream.id,
            'memory',
            'active',
            '星の記録を残した',
            self.message.id,
        )

        class Speaker:
            def __init__(self):
                self.contexts = []

            async def speak(inner_self, context):
                inner_self.contexts.append(context)
                return '返事'

        settings = Settings(
            discord_token='',
            discord_client_id=None,
            openai_api_key='',
            openai_model='',
            database_file=Path(self.temp_dir.name) / 'references.sqlite3',
            listening_channel_ids=frozenset(),
            yuno_call_names=('ゆの', '唯乃', 'yuno'),
            log_level='INFO',
        )
        speaker = Speaker()
        pipeline = ConversationPipeline(
            MessageRouter(settings, self.conversations),
            self.conversations,
            self.context,
            speaker,
            reference_selector=self.selector,
        )
        incoming = IncomingMessage(
            discord_message_id='directed-1',
            discord_channel_id='10',
            discord_guild_id='1',
            stream_kind='channel',
            author_id='7',
            author_name='A',
            author_is_bot=False,
            bot_user_id='99',
            mentions_bot=True,
            raw_content='<@99> 星の記録を思い出した',
            created_at='2026-01-01T00:00:00+00:00',
            reply_to_discord_message_id=None,
        )

        result = await pipeline.process(incoming)

        self.assertTrue(result.should_send)
        self.assertEqual(speaker.contexts[0].references[0].public_id, mark.public_id)
        self.assertEqual(
            speaker.contexts[0].references[0].content,
            '星の記録を残した',
        )
