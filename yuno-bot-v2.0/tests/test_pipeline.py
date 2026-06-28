from pathlib import Path
import tempfile
import unittest

from yuno.config import Settings
from yuno.conversation.context import ContextBuilder, SpeakerContext
from yuno.conversation.repository import ConversationRepository
from yuno.discord.routing import MessageRouter
from yuno.infra.database import Database
from yuno.messages import IncomingMessage, SentMessage
from yuno.pipeline import ConversationPipeline


class RecordingSpeaker:
    def __init__(self):
        self.contexts = []

    async def speak(self, context: SpeakerContext) -> str:
        self.contexts.append(context)
        return "自然な返事"


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "pipeline.sqlite3")
        await self.database.open()
        self.repository = ConversationRepository(self.database)
        self.speaker = RecordingSpeaker()
        self.settings = Settings(
            discord_token="",
            discord_client_id=None,
            openai_api_key="",
            openai_model="",
            database_file=Path(self.temp_dir.name) / "pipeline.sqlite3",
            listening_channel_ids=frozenset({10}),
            yuno_call_names=("ゆの", "唯乃", "yuno"),
            log_level="INFO",
        )
        self.pipeline = ConversationPipeline(
            MessageRouter(self.settings, self.repository),
            self.repository,
            ContextBuilder(self.repository),
            self.speaker,
        )

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    def incoming(
        self,
        message_id: str,
        content: str,
        channel_id: str = "10",
        *,
        mention: bool = False,
        guild_id="1",
        reply_to=None,
    ) -> IncomingMessage:
        return IncomingMessage(
            discord_message_id=message_id,
            discord_channel_id=channel_id,
            discord_guild_id=guild_id,
            stream_kind="dm" if guild_id is None else "channel",
            author_id="7",
            author_name="こはる",
            author_is_bot=False,
            bot_user_id="99",
            mentions_bot=mention,
            raw_content=content,
            created_at="2026-01-01T00:00:00+00:00",
            reply_to_discord_message_id=reply_to,
        )

    async def test_ignored_message_is_not_stored(self) -> None:
        result = await self.pipeline.process(
            self.incoming("1", "対象外", channel_id="20")
        )
        self.assertFalse(result.should_send)
        self.assertIsNone(result.stream_id)
        row = await (await self.database.connection.execute(
            "SELECT COUNT(*) AS count FROM messages"
        )).fetchone()
        self.assertEqual(row["count"], 0)

    async def test_listening_message_is_saved_without_speaker(self) -> None:
        result = await self.pipeline.process(self.incoming("1", "近くの会話"))
        self.assertFalse(result.should_send)
        self.assertIsNotNone(result.stream_id)
        self.assertEqual(await self.repository.count_messages(result.stream_id), 1)
        self.assertEqual(self.speaker.contexts, [])

    async def test_reply_generation_does_not_save_assistant_before_send(self) -> None:
        result = await self.pipeline.process(
            self.incoming("1", "<@99> 話そう", mention=True)
        )
        self.assertTrue(result.should_send)
        self.assertEqual(result.reply_mode, "discord_reply")
        self.assertEqual(result.reply_to_discord_message_id, "1")
        self.assertEqual(await self.repository.count_messages(result.stream_id), 1)
        self.assertEqual(len(self.speaker.contexts), 1)

        await self.pipeline.record_sent_assistant(
            result,
            SentMessage("2", "99", "ゆの", result.reply_text, "2026-01-01T00:00:01+00:00"),
        )
        self.assertEqual(await self.repository.count_messages(result.stream_id), 2)
        self.assertTrue(await self.repository.is_assistant_message("2"))

    async def test_context_contains_only_same_stream_and_no_route_metadata(self) -> None:
        other = await self.repository.get_or_create_stream("channel", "20", "1")
        dm = await self.repository.get_or_create_stream("dm", "30", None)
        await self.repository.append(other.id, "other", "user", "8", "A", "別channel")
        await self.repository.append(dm.id, "private", "user", "7", "A", "DMの秘密")

        await self.pipeline.process(self.incoming("1", "ふつうの前置き"))
        await self.pipeline.process(self.incoming("2", "<@99> 続けよう", mention=True))
        history = self.speaker.contexts[-1].history
        rendered = "\n".join(item["content"] for item in history)

        self.assertIn("ふつうの前置き", rendered)
        self.assertIn("続けよう", rendered)
        self.assertNotIn("別channel", rendered)
        self.assertNotIn("DMの秘密", rendered)
        self.assertNotIn("mention", rendered)
        self.assertNotIn("discord_reply", rendered)
        self.assertNotIn("呼びかけられた", rendered)
