from pathlib import Path
import tempfile
import unittest

from yuno.care.models import (
    CareMarkCandidate,
    CareReadResult,
    ReadCueUpdate,
)
from yuno.care.service import CareService
from yuno.care_marks.repository import CareMarkRepository
from yuno.care_marks.service import CareMarkService
from yuno.config import Settings
from yuno.conversation.context import ContextBuilder
from yuno.conversation.repository import ConversationRepository
from yuno.discord.routing import MessageRouter
from yuno.infra.database import Database
from yuno.messages import IncomingMessage
from yuno.pipeline import ConversationPipeline
from yuno.read_cues.repository import ReadCueRepository
from yuno.read_cues.service import ReadCueService


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
        marks = await self.marks.list_for_stream(
            self.stream.id, ('attention',), ('open',)
        )
        self.assertEqual(len(marks), 1)

    async def test_read_cue_updates_are_upserted_for_resolved_mark(self) -> None:
        first = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(
                care_mark_candidates=(
                    CareMarkCandidate('attention', 'open', '星の話'),
                ),
                read_cue_updates=(
                    ReadCueUpdate(' ＳＴＡＲ ', 0.2, candidate_text='星の話'),
                ),
            ),
        )
        public_id = first.created_care_mark_ids[0]
        mark = await self.marks.get_by_public_id(public_id)
        initial = await self.cues.list_for_mark(mark.id)

        second = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(read_cue_updates=(
                ReadCueUpdate(
                    'star', 0.8, care_mark_public_id=public_id
                ),
            )),
        )
        updated = await self.cues.list_for_mark(mark.id)

        self.assertEqual(len(initial), 1)
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0].id, initial[0].id)
        self.assertEqual(updated[0].weight, 0.8)
        self.assertEqual(second.upserted_read_cue_ids, (initial[0].id,))

    async def test_read_cue_never_becomes_speaker_reference(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'attention', 'open', '星の話'
        )
        await self.cues.upsert(mark.id, '星', 0.5)
        state = await self.service.current_state(self.stream.id)
        request = await self.service.build_request(
            self.stream.id, '星について', 0.0, 0.5, state
        )

        context = await ContextBuilder(self.conversations).build(self.stream.id)

        self.assertEqual(request.read_cues[0]['term'], '星')
        self.assertEqual(context.references, ())
        self.assertNotIn('星', str(context.references))

    async def test_cue_for_hidden_mark_is_not_in_care_state(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'memory', 'hidden', 'hidden text'
        )
        await self.cues.upsert(mark.id, 'hidden cue', 0.7)

        state = await self.service.current_state(self.stream.id)

        self.assertEqual(state.care_marks, ())
        self.assertEqual(state.read_cues, ())

    async def test_listening_care_path_uses_no_legacy_tables(self) -> None:
        await self.marks.create(
            self.stream.id, 'attention', 'open', '星の話'
        )

        class Reader:
            def __init__(self):
                self.requests = []

            async def read(inner_self, request):
                inner_self.requests.append(request)
                return CareReadResult(care_mark_candidates=(
                    CareMarkCandidate('memory', 'draft', '残す断片'),
                ))

        class Speaker:
            async def speak(self, context):
                raise AssertionError('listening-only turn should remain silent')

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
        reader = Reader()
        pipeline = ConversationPipeline(
            MessageRouter(settings, self.conversations),
            self.conversations,
            ContextBuilder(self.conversations),
            Speaker(),
            reader,
            self.service,
        )
        incoming = IncomingMessage(
            discord_message_id='listening-1',
            discord_channel_id='10',
            discord_guild_id='1',
            stream_kind='channel',
            author_id='7',
            author_name='A',
            author_is_bot=False,
            bot_user_id='99',
            mentions_bot=False,
            raw_content='星の話をしている',
            created_at='2026-01-01T00:00:00+00:00',
            reply_to_discord_message_id=None,
        )

        result = await pipeline.process(incoming)

        self.assertFalse(result.should_send)
        self.assertEqual(len(reader.requests), 1)
        marks = await self.marks.list_for_stream(self.stream.id)
        self.assertEqual(
            {mark.text for mark in marks}, {'星の話', '残す断片'}
        )
