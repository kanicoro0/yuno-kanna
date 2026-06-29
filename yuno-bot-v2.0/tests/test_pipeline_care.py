from pathlib import Path
import tempfile
import unittest

from yuno.attention.repository import AttentionRepository
from yuno.attention.service import AttentionService
from yuno.care.models import (
    AttentionCandidate, CareReadResult, InterestUpdate, MemoryCandidate,
)
from yuno.care.service import CareService
from yuno.config import Settings
from yuno.conversation.context import ContextBuilder
from yuno.conversation.repository import ConversationRepository
from yuno.discord.routing import MessageRouter
from yuno.infra.database import Database
from yuno.interest.repository import InterestRepository
from yuno.interest.service import InterestService
from yuno.memory.repository import MemoryMarkRepository
from yuno.memory.service import MemoryMarkService
from yuno.messages import IncomingMessage
from yuno.pipeline import ConversationPipeline


class FakeCareReader:
    def __init__(self, result=CareReadResult()):
        self.result = result
        self.requests = []

    async def read(self, request):
        self.requests.append(request)
        return self.result


class RecordingSpeaker:
    def __init__(self, fail=False):
        self.fail = fail
        self.contexts = []

    async def speak(self, context):
        self.contexts.append(context)
        if self.fail:
            raise RuntimeError("speaker failed")
        return "返事"


class PipelineCareTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "pipeline-care.sqlite3")
        await self.database.open()
        self.conversations = ConversationRepository(self.database)
        self.memory = MemoryMarkService(MemoryMarkRepository(self.database))
        self.attention = AttentionService(AttentionRepository(self.database))
        self.interest = InterestService(InterestRepository(self.database))
        self.settings = Settings(
            discord_token="", discord_client_id=None, openai_api_key="", openai_model="",
            database_file=Path(self.temp_dir.name) / "pipeline-care.sqlite3",
            listening_channel_ids=frozenset({10}),
            yuno_call_names=("ゆの", "唯乃", "yuno"), log_level="INFO",
        )

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    def incoming(self, message_id: str, content: str, mention=False) -> IncomingMessage:
        return IncomingMessage(
            discord_message_id=message_id, discord_channel_id="10",
            discord_guild_id="1", stream_kind="channel", author_id="7",
            author_name="A", author_is_bot=False, bot_user_id="99",
            mentions_bot=mention, raw_content=content,
            created_at="2026-01-01T00:00:00+00:00",
            reply_to_discord_message_id=None,
        )

    def pipeline(self, reader, speaker):
        care = CareService(
            self.conversations, self.memory, self.attention, self.interest
        )
        return ConversationPipeline(
            MessageRouter(self.settings, self.conversations),
            self.conversations,
            ContextBuilder(
                self.conversations, self.memory, self.attention, self.interest
            ),
            speaker,
            reader,
            care,
        )

    async def test_directed_message_calls_care_and_applies_candidates(self) -> None:
        reader = FakeCareReader(CareReadResult(
            memory_candidates=(MemoryCandidate("大事な断片", "pin", "active", 0.8),),
            attention_candidates=(AttentionCandidate("開いた話", 0.6),),
            interest_updates=(InterestUpdate("星", 0.4),),
        ))
        speaker = RecordingSpeaker()
        result = await self.pipeline(reader, speaker).process(
            self.incoming("1", "<@99> 聞いて", mention=True)
        )
        self.assertTrue(result.should_send)
        self.assertEqual(len(reader.requests), 1)
        self.assertEqual(reader.requests[0].addressing_strength, 1.0)
        stream_id = result.stream_id
        self.assertEqual(len(await self.memory.references_for_stream(stream_id)), 1)
        self.assertEqual(len(await self.attention.references_for_stream(stream_id)), 1)
        self.assertEqual(len(await self.interest.references_for_stream(stream_id)), 1)
        rendered = str(speaker.contexts[0])
        self.assertNotIn("salience", rendered)
        self.assertNotIn("routing", rendered)
        self.assertNotIn("reason", rendered)

    async def test_unmatched_listening_message_is_store_only_without_care(self) -> None:
        reader = FakeCareReader(CareReadResult(should_speak=True))
        speaker = RecordingSpeaker()
        result = await self.pipeline(reader, speaker).process(
            self.incoming("1", "ただの近くの会話")
        )
        self.assertFalse(result.should_send)
        self.assertEqual(reader.requests, [])
        self.assertEqual(speaker.contexts, [])
        self.assertEqual(await self.conversations.count_messages(result.stream_id), 1)

    async def test_matching_interest_calls_care_but_speaks_only_when_allowed(self) -> None:
        stream = await self.conversations.get_or_create_stream("channel", "10", "1")
        await self.interest.repository.upsert_term(stream.id, "天体観測", 0.5, "manual")
        quiet_reader = FakeCareReader(CareReadResult(should_speak=False))
        quiet_speaker = RecordingSpeaker()
        quiet = await self.pipeline(quiet_reader, quiet_speaker).process(
            self.incoming("1", "今夜は天体観測の話をしてる")
        )
        self.assertFalse(quiet.should_send)
        self.assertEqual(len(quiet_reader.requests), 1)
        self.assertEqual(quiet_speaker.contexts, [])

        one_flag_reader = FakeCareReader(CareReadResult(
            wants_to_speak=False, should_speak=True
        ))
        one_flag_speaker = RecordingSpeaker()
        one_flag = await self.pipeline(one_flag_reader, one_flag_speaker).process(
            self.incoming("one-flag", "天体観測はどうなるかな")
        )
        self.assertFalse(one_flag.should_send)
        self.assertEqual(one_flag_speaker.contexts, [])

        speaking_reader = FakeCareReader(CareReadResult(
            wants_to_speak=True, should_speak=True
        ))
        speaking_speaker = RecordingSpeaker()
        speaking = await self.pipeline(speaking_reader, speaking_speaker).process(
            self.incoming("2", "天体観測、晴れるかな")
        )
        self.assertTrue(speaking.should_send)
        self.assertEqual(speaking.reply_mode, "plain")
        self.assertEqual(len(speaking_speaker.contexts), 1)

    async def test_speaker_failure_keeps_user_message_without_assistant(self) -> None:
        reader = FakeCareReader()
        pipeline = self.pipeline(reader, RecordingSpeaker(fail=True))
        with self.assertRaises(RuntimeError):
            await pipeline.process(self.incoming("1", "<@99> 聞いて", mention=True))
        stream = await self.conversations.get_or_create_stream("channel", "10", "1")
        messages = await self.conversations.recent(stream.id)
        self.assertEqual([(item.role, item.content) for item in messages], [("user", "聞いて")])
