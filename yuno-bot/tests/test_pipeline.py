import asyncio
from pathlib import Path
import tempfile
import unittest

from yuno.care.models import CareReadRequest, CareReadResult
from yuno.care.service import CareApplication
from yuno.config import Settings
from yuno.conversation.context import ContextBuilder, SpeakerContext
from yuno.conversation.repository import ConversationRepository
from yuno.discord.routing import MessageRouter
from yuno.infra.database import Database
from yuno.messages import IncomingMessage, SentMessage
from yuno.pipeline import ConversationPipeline, ObservationTicket


class RecordingSpeaker:
    def __init__(self):
        self.contexts = []

    async def speak(self, context: SpeakerContext) -> str:
        self.contexts.append(context)
        return "natural reply"


class FakeCareReader:
    def __init__(self, result: CareReadResult):
        self.result = result
        self.requests = []

    async def read(self, request: CareReadRequest) -> CareReadResult:
        self.requests.append(request)
        return self.result


class FakeCareService:
    async def current_state(self, stream_id):
        return type("State", (), {"care_marks": (), "read_cues": ()})()

    async def build_request(
        self,
        stream_id,
        current_message,
        addressing_strength,
        cue_salience_value,
        state,
        route_reason="",
        reply_mode="none",
    ):
        return CareReadRequest(
            current_message=current_message,
            recent_messages=(),
            care_marks=(),
            read_cues=(),
            addressing_strength=addressing_strength,
            cue_salience=cue_salience_value,
            route_reason=route_reason,
            reply_mode=reply_mode,
        )

    async def apply(self, stream_id, source_message_id, result, source_content=''):
        return CareApplication()


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
        author_is_bot: bool = False,
        guild_id="1",
        reply_to=None,
        created_at="2026-01-01T00:00:00+00:00",
    ) -> IncomingMessage:
        return IncomingMessage(
            discord_message_id=message_id,
            discord_channel_id=channel_id,
            discord_guild_id=guild_id,
            stream_kind="dm" if guild_id is None else "channel",
            author_id="7",
            author_name="koharu",
            author_is_bot=author_is_bot,
            bot_user_id="99",
            mentions_bot=mention,
            raw_content=content,
            created_at=created_at,
            reply_to_discord_message_id=reply_to,
        )

    async def test_ignored_message_is_not_stored(self) -> None:
        result = await self.pipeline.process(
            self.incoming("1", "outside", channel_id="20")
        )
        self.assertFalse(result.should_send)
        self.assertIsNone(result.stream_id)
        row = await (await self.database.connection.execute(
            "SELECT COUNT(*) AS count FROM messages"
        )).fetchone()
        self.assertEqual(row["count"], 0)

    async def test_ignored_bot_message_does_not_create_a_turn_or_store(self) -> None:
        turn = await self.pipeline.intake(
            self.incoming("bot", "bot message", author_is_bot=True)
        )

        self.assertIsNone(turn)
        row = await (await self.database.connection.execute(
            "SELECT COUNT(*) AS count FROM messages"
        )).fetchone()
        self.assertEqual(row["count"], 0)

    async def test_single_dm_is_stored_then_processed_as_one_turn(self) -> None:
        incoming = self.incoming("dm-1", "talk in dm", channel_id="30", guild_id=None)

        turn = await self.pipeline.intake(incoming)

        self.assertIsNotNone(turn)
        stored = await self.repository.find_by_discord_message_id("dm-1")
        self.assertEqual(turn.source_user_message_ids, (stored.id,))
        self.assertEqual(turn.content, "talk in dm")
        result = await self.pipeline.process_turn(turn)
        self.assertTrue(result.should_send)
        self.assertEqual(result.reply_mode, "plain")

    async def test_turn_uses_stored_content_without_route_metadata(self) -> None:
        turn = await self.pipeline.intake(
            self.incoming("turn-1", "<@99> continue", mention=True)
        )

        stored = await self.repository.find_by_discord_message_id("turn-1")
        self.assertEqual(turn.source_user_message_ids, (stored.id,))
        self.assertEqual(stored.discord_message_id, "turn-1")
        result = await self.pipeline.process_turn(turn)
        rendered = str(self.speaker.contexts[-1].history)
        self.assertTrue(result.should_send)
        self.assertEqual(result.reply_mode, "discord_reply")
        self.assertEqual(self.speaker.contexts[-1].route_reason, "mention")
        self.assertIn("continue", rendered)
        self.assertNotIn("mention", rendered)
        self.assertNotIn("discord_reply", rendered)

    async def test_reply_to_yuno_still_uses_discord_reply(self) -> None:
        stream = await self.repository.get_or_create_stream("channel", "10", "1")
        await self.repository.append(
            stream.id, "yuno-1", "assistant", "99", "yuno", "previous reply"
        )

        result = await self.pipeline.process(
            self.incoming("reply-1", "continue", reply_to="yuno-1")
        )

        self.assertTrue(result.should_send)
        self.assertEqual(result.reply_mode, "discord_reply")
        self.assertEqual(result.reply_to_discord_message_id, "reply-1")

    async def test_care_reader_can_enable_plain_listening_reply_for_triggered_message(self) -> None:
        care_reader = FakeCareReader(CareReadResult(
            decision_made=True,
            should_speak=True,
            reply_reason="followup",
            speaker_note="plain listening followup",
        ))
        pipeline = ConversationPipeline(
            MessageRouter(self.settings, self.repository),
            self.repository,
            ContextBuilder(self.repository),
            self.speaker,
            care_reader=care_reader,
            care_service=FakeCareService(),
        )

        result = await pipeline.process(self.incoming("followup", "これを覚えて plain followup?"))

        self.assertTrue(result.should_send)
        self.assertEqual(result.reply_mode, "plain")
        self.assertEqual(care_reader.requests[-1].route_reason, "listening_only")
        self.assertEqual(self.speaker.contexts[-1].route_reason, "listening_only")
        self.assertEqual(self.speaker.contexts[-1].reply_reason, "followup")
        self.assertEqual(
            self.speaker.contexts[-1].speaker_note,
            "plain listening followup",
        )

    async def test_care_reader_can_silence_hard_route(self) -> None:
        care_reader = FakeCareReader(CareReadResult(
            decision_made=True,
            should_speak=False,
            reply_reason="none",
        ))
        pipeline = ConversationPipeline(
            MessageRouter(self.settings, self.repository),
            self.repository,
            ContextBuilder(self.repository),
            self.speaker,
            care_reader=care_reader,
            care_service=FakeCareService(),
        )

        result = await pipeline.process(
            self.incoming("mention-silent", "<@99> no need", mention=True)
        )

        self.assertFalse(result.should_send)
        self.assertIsNotNone(result.stream_id)
        self.assertEqual(care_reader.requests[-1].route_reason, "mention")
        self.assertEqual(care_reader.requests[-1].reply_mode, "discord_reply")
        self.assertEqual(self.speaker.contexts, [])

    async def test_router_reply_falls_back_when_care_reader_makes_no_decision(self) -> None:
        care_reader = FakeCareReader(CareReadResult())
        pipeline = ConversationPipeline(
            MessageRouter(self.settings, self.repository),
            self.repository,
            ContextBuilder(self.repository),
            self.speaker,
            care_reader=care_reader,
            care_service=FakeCareService(),
        )

        result = await pipeline.process(
            self.incoming("mention-fallback", "<@99> fallback", mention=True)
        )

        self.assertTrue(result.should_send)
        self.assertEqual(result.reply_mode, "discord_reply")
        self.assertEqual(care_reader.requests[-1].route_reason, "mention")
        self.assertEqual(len(self.speaker.contexts), 1)

    async def test_listening_message_is_saved_without_speaker(self) -> None:
        result = await self.pipeline.process(self.incoming("1", "nearby talk"))
        self.assertFalse(result.should_send)
        self.assertIsNotNone(result.stream_id)
        self.assertEqual(await self.repository.count_messages(result.stream_id), 1)
        self.assertEqual(self.speaker.contexts, [])

    async def test_weak_name_message_is_saved_without_immediate_speaker(self) -> None:
        result = await self.pipeline.process(self.incoming("weak", "しょうゆの作り方"))
        self.assertFalse(result.should_send)
        self.assertIsNotNone(result.stream_id)
        self.assertEqual(await self.repository.count_messages(result.stream_id), 1)
        self.assertEqual(self.speaker.contexts, [])

    async def test_reply_generation_does_not_save_assistant_before_send(self) -> None:
        result = await self.pipeline.process(
            self.incoming("1", "<@99> talk", mention=True)
        )
        self.assertTrue(result.should_send)
        self.assertEqual(result.reply_mode, "discord_reply")
        self.assertEqual(result.reply_to_discord_message_id, "1")
        self.assertEqual(await self.repository.count_messages(result.stream_id), 1)
        self.assertEqual(len(self.speaker.contexts), 1)

        await self.pipeline.record_sent_assistant(
            result,
            SentMessage("2", "99", "yuno", result.reply_text, "2026-01-01T00:00:01+00:00"),
        )
        self.assertEqual(await self.repository.count_messages(result.stream_id), 2)
        self.assertTrue(await self.repository.is_assistant_message("2"))

    async def test_context_contains_only_same_stream_and_no_route_metadata(self) -> None:
        other = await self.repository.get_or_create_stream("channel", "20", "1")
        dm = await self.repository.get_or_create_stream("dm", "30", None)
        await self.repository.append(other.id, "other", "user", "8", "A", "other channel")
        await self.repository.append(dm.id, "private", "user", "7", "A", "dm secret")

        await self.pipeline.process(self.incoming("1", "normal preface"))
        await self.pipeline.process(self.incoming("2", "<@99> continue", mention=True))
        history = self.speaker.contexts[-1].history
        rendered = "\n".join(item["content"] for item in history)

        self.assertIn("normal preface", rendered)
        self.assertIn("continue", rendered)
        self.assertNotIn("other channel", rendered)
        self.assertNotIn("dm secret", rendered)
        self.assertNotIn("mention", rendered)
        self.assertNotIn("discord_reply", rendered)

    async def test_directed_context_uses_only_six_recent_messages(self) -> None:
        for index in range(7):
            await self.pipeline.process(self.incoming(str(index), f"nearby {index}"))
        await self.pipeline.process(
            self.incoming("directed", "<@99> current", mention=True)
        )
        history = self.speaker.contexts[-1].history
        self.assertEqual(len(history), 6)
        self.assertNotIn("nearby 0", str(history))
        self.assertIn("current", str(history))

    async def test_directed_context_drops_messages_before_long_gap(self) -> None:
        await self.pipeline.process(self.incoming(
            "old", "old topic", created_at="2026-01-01T03:00:00+00:00"
        ))
        await self.pipeline.process(self.incoming(
            "near", "near topic", created_at="2026-01-01T04:00:00+00:00"
        ))
        await self.pipeline.process(self.incoming(
            "current", "<@99> current", mention=True,
            created_at="2026-01-01T04:05:00+00:00",
        ))

        history = self.speaker.contexts[-1].history
        rendered = str(history)
        self.assertNotIn("old topic", rendered)
        self.assertIn("near topic", rendered)
        self.assertIn("current", rendered)

    async def test_pre_send_auto_maintenance_is_scheduled_not_awaited(self) -> None:
        called = asyncio.Event()
        release = asyncio.Event()

        class BlockingMaintenance:
            def __init__(self):
                self.calls = []

            async def auto_close_after_activity(self, stream_id, **kwargs):
                self.calls.append((stream_id, kwargs))
                called.set()
                await release.wait()

        class ApplyingCareService(FakeCareService):
            async def apply(self, stream_id, source_message_id, result, source_content=''):
                return CareApplication(created_care_mark_ids=('care_0001',))

        maintenance = BlockingMaintenance()
        pipeline = ConversationPipeline(
            MessageRouter(self.settings, self.repository),
            self.repository,
            ContextBuilder(self.repository),
            self.speaker,
            care_reader=FakeCareReader(CareReadResult()),
            care_service=ApplyingCareService(),
            maintenance_service=maintenance,
        )

        result = await asyncio.wait_for(
            pipeline.process(self.incoming('mention-maint', '<@99> hi', mention=True)),
            0.2,
        )

        self.assertTrue(result.should_send)
        await asyncio.wait_for(called.wait(), 0.2)
        self.assertEqual(
            maintenance.calls,
            [(result.stream_id, {'protected_public_ids': ('care_0001',)})],
        )
        release.set()
        await asyncio.gather(*tuple(pipeline._background_tasks))

    async def test_post_send_auto_maintenance_is_scheduled_not_awaited(self) -> None:
        called = asyncio.Event()
        release = asyncio.Event()

        class BlockingMaintenance:
            def __init__(self):
                self.calls = []

            async def auto_close_after_activity(self, stream_id, **kwargs):
                self.calls.append((stream_id, kwargs))
                called.set()
                await release.wait()

        class ApplyingCareService(FakeCareService):
            async def apply(self, stream_id, source_message_id, result, source_content=''):
                return CareApplication(created_care_mark_ids=('care_0002',))

        maintenance = BlockingMaintenance()
        pipeline = ConversationPipeline(
            MessageRouter(self.settings, self.repository),
            self.repository,
            ContextBuilder(self.repository),
            self.speaker,
            care_reader=FakeCareReader(CareReadResult()),
            care_service=ApplyingCareService(),
            maintenance_service=maintenance,
        )

        stream = await self.repository.get_or_create_stream('channel', '10', '1')
        application = await asyncio.wait_for(
            pipeline.observe_after_send(ObservationTicket(
                stream_id=stream.id,
                source_user_message_ids=(1,),
                user_content='覚えておいて',
                route_reason='listening_only',
                pre_care_completed=False,
            )),
            0.2,
        )

        self.assertEqual(application.created_care_mark_ids, ('care_0002',))
        await asyncio.wait_for(called.wait(), 0.2)
        self.assertEqual(
            maintenance.calls,
            [(stream.id, {'protected_public_ids': ('care_0002',)})],
        )
        release.set()
        await asyncio.gather(*tuple(pipeline._background_tasks))
