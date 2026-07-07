from pathlib import Path
import tempfile
import unittest

from yuno.care.models import (
    CareMarkCandidate,
    CareReadResult,
    ReadCueUpdate,
)
from yuno.care.service import (
    CareService,
    CareState,
    immediate_care_decision,
)
from yuno.care_marks.repository import CareMarkRepository
from yuno.care_marks.service import CareMarkService
from yuno.config import Settings
from yuno.conversation.context import ContextBuilder
from yuno.conversation.repository import ConversationRepository
from yuno.discord.routing import MessageRouter
from yuno.infra.database import Database
from yuno.messages import IncomingMessage, SentMessage
from yuno.pipeline import ConversationPipeline
from yuno.read_cues.repository import ReadCueRepository
from yuno.read_cues.service import ReadCueService


class RecordingReader:
    def __init__(self, result=None):
        self.result = result or CareReadResult()
        self.requests = []

    async def read(self, request):
        self.requests.append(request)
        return self.result


class RecordingSpeaker:
    def __init__(self):
        self.contexts = []

    async def speak(self, context):
        self.contexts.append(context)
        return '自然な返事'


class CareServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / 'care.sqlite3')
        await self.database.open()
        self.conversations = ConversationRepository(self.database)
        self.stream = await self.conversations.get_or_create_stream(
            'channel', '10', '1'
        )
        self.message = await self.conversations.append(
            self.stream.id, 'message-1', 'user', '7', 'A', 'conversation'
        )
        self.marks = CareMarkService(CareMarkRepository(self.database))
        self.cues = ReadCueService(ReadCueRepository(self.database))
        self.service = CareService(
            self.conversations, self.marks, self.cues
        )

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    def test_explicit_language_triggers_immediate_care(self) -> None:
        examples = (
            ('これを覚えて', 'explicit_memory'),
            ('あとで見たい', 'attention_language'),
            ('こはると呼んで', 'name_preference'),
            ('青色が好き', 'preference'),
            ('締切を忘れそう', 'schedule_or_task'),
        )
        for content, reason in examples:
            with self.subTest(content=content):
                decision = immediate_care_decision(content, CareState())
                self.assertTrue(decision.run)
                self.assertEqual(decision.reason, reason)

    def pipeline(self, reader, speaker=None):
        settings = Settings(
            discord_token='',
            discord_client_id=None,
            openai_api_key='',
            openai_model='',
            database_file=Path(self.temp_dir.name) / 'care.sqlite3',
            listening_channel_ids=frozenset({10}),
            yuno_call_names=('ゆの', '唯乃', 'yuno'),
            log_level='INFO',
        )
        return ConversationPipeline(
            MessageRouter(settings, self.conversations),
            self.conversations,
            ContextBuilder(self.conversations),
            speaker or RecordingSpeaker(),
            reader,
            self.service,
        )

    @staticmethod
    def incoming(message_id, content, *, mention=False):
        return IncomingMessage(
            discord_message_id=message_id,
            discord_channel_id='10',
            discord_guild_id='1',
            stream_kind='channel',
            author_id='7',
            author_name='A',
            author_is_bot=False,
            bot_user_id='99',
            mentions_bot=mention,
            raw_content=content,
            created_at='2026-01-01T00:00:00+00:00',
            reply_to_discord_message_id=None,
        )

    async def test_directed_reply_reads_care_before_speech_and_keeps_logs(self) -> None:
        reader = RecordingReader(CareReadResult())
        pipeline = self.pipeline(reader)

        result = await pipeline.process(
            self.incoming('low-reply', '今日はいい天気だね', mention=True)
        )
        await pipeline.record_sent_assistant(
            result,
            SentMessage('reply-1', '99', 'ゆの', result.reply_text, 'now'),
        )
        application = await pipeline.observe_after_send(
            result.observation_ticket
        )

        self.assertIsNone(application)
        self.assertEqual(len(reader.requests), 1)
        self.assertEqual(result.care_mark_changes, ())
        self.assertEqual(
            await self.conversations.count_messages(self.stream.id),
            3,
        )
        self.assertTrue(
            await self.conversations.is_assistant_message('reply-1')
        )
        self.assertEqual(await self.marks.list_for_stream(self.stream.id), [])

    async def test_explicit_memory_and_name_preference_runs_before_send(self) -> None:
        reader = RecordingReader(CareReadResult(care_mark_candidates=(
            CareMarkCandidate('memory', 'draft', 'こはると呼ぶ'),
        )))
        pipeline = self.pipeline(reader)

        result = await pipeline.process(
            self.incoming(
                'remember-name',
                '名前はこはる。そう呼んで、覚えて',
                mention=True,
            )
        )
        application = await pipeline.observe_after_send(
            result.observation_ticket
        )

        self.assertEqual(len(reader.requests), 1)
        self.assertIsNone(application)
        self.assertEqual(len(result.care_mark_changes), 1)

    async def test_low_signal_listening_skips_care(self) -> None:
        reader = RecordingReader(CareReadResult(care_mark_candidates=(
            CareMarkCandidate('attention', 'open', '作られてはいけない'),
        )))
        pipeline = self.pipeline(reader)

        result = await pipeline.process(
            self.incoming('low-listening', '今日はいい天気だね')
        )

        self.assertFalse(result.should_send)
        self.assertEqual(reader.requests, [])
        self.assertEqual(result.care_mark_changes, ())
        self.assertEqual(await self.marks.list_for_stream(self.stream.id), [])
        self.assertEqual(
            await self.conversations.count_messages(self.stream.id),
            2,
        )

    async def test_strong_cue_runs_listening_reader(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'memory', 'active', '星の話'
        )
        await self.cues.upsert(mark.id, '星', 0.6)
        reader = RecordingReader()
        pipeline = self.pipeline(reader)

        result = await pipeline.process(
            self.incoming('strong-cue', '星が見える')
        )

        self.assertFalse(result.should_send)
        self.assertEqual(len(reader.requests), 1)
        self.assertGreaterEqual(reader.requests[0].cue_salience, 0.5)

    async def test_creates_care_mark_and_downgrades_sensitive_memory(self) -> None:
        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(care_mark_candidates=(
                CareMarkCandidate(
                    'memory', 'active', '通院している', sensitive=True
                ),
            )),
        )

        self.assertEqual(len(application.created_care_mark_ids), 1)
        mark = await self.marks.get_by_public_id(
            application.created_care_mark_ids[0]
        )
        self.assertEqual((mark.kind, mark.status), ('memory', 'draft'))
        self.assertEqual(application.affected_care_marks, (mark,))

    async def test_similar_open_attention_is_touched_not_duplicated(self) -> None:
        existing = await self.marks.create(
            self.stream.id, 'attention', 'open', '星 の話'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(care_mark_candidates=(
                CareMarkCandidate('attention', 'open', '星・の話'),
            )),
        )

        self.assertEqual(application.created_care_mark_ids, ())
        self.assertEqual(application.touched_care_mark_ids, (existing.public_id,))
        self.assertEqual(
            tuple(mark.public_id for mark in application.affected_care_marks),
            (existing.public_id,),
        )

    async def test_read_cue_update_links_to_created_candidate(self) -> None:
        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(
                care_mark_candidates=(
                    CareMarkCandidate('memory', 'active', '星の話'),
                ),
                read_cue_updates=(
                    ReadCueUpdate('星', 0.6, candidate_text='星の話'),
                ),
            ),
        )

        self.assertEqual(len(application.upserted_read_cue_ids), 1)
        cues = await self.cues.list_for_stream(self.stream.id)
        self.assertEqual(cues[0].term, '星')

    async def test_touch_id_links_to_existing_mark(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'memory', 'active', '月の話'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(touch_care_mark_ids=(mark.public_id,)),
        )

        self.assertEqual(application.touched_care_mark_ids, (mark.public_id,))
        self.assertEqual(application.affected_care_marks[0].public_id, mark.public_id)
