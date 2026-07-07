from datetime import datetime, timezone
from types import SimpleNamespace
import asyncio
import unittest

from yuno.discord.events import (
    ConversationRuntime,
    finalize_sent_message,
    handle_message,
    process_turn_with_typing,
    send_result,
)
from yuno.discord.input import to_incoming_message
from yuno.pipeline import PipelineResult
from yuno.turns import PipelineTurn, TurnBuffer, TurnManager


class FakeTyping:
    def __init__(self, channel):
        self.channel = channel

    async def __aenter__(self):
        self.channel.typing_enters += 1

    async def __aexit__(self, exc_type, exc, traceback):
        self.channel.typing_exits += 1


class FakeChannel:
    def __init__(self):
        self.id = 10
        self.calls = []
        self.typing_enters = 0
        self.typing_exits = 0

    def typing(self):
        return FakeTyping(self)

    async def send(self, content, **kwargs):
        self.calls.append((content, kwargs))
        return "plain-sent"


class FakeMessage:
    def __init__(self):
        self.id = 100
        self.channel = FakeChannel()
        self.guild = SimpleNamespace(id=1)
        self.author = SimpleNamespace(id=7, display_name="こはる", bot=False)
        self.mentions = []
        self.content = "本文"
        self.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.reference = SimpleNamespace(message_id=50)
        self.reply_calls = []

    async def reply(self, content, **kwargs):
        self.reply_calls.append((content, kwargs))
        return "reply-sent"


class DiscordBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_discord_message_is_converted_at_entry(self) -> None:
        message = FakeMessage()
        bot_user = SimpleNamespace(id=99)
        message.mentions = [bot_user]
        incoming = to_incoming_message(message, bot_user)

        self.assertEqual(incoming.discord_message_id, "100")
        self.assertEqual(incoming.discord_channel_id, "10")
        self.assertEqual(incoming.discord_guild_id, "1")
        self.assertEqual(incoming.reply_to_discord_message_id, "50")
        self.assertTrue(incoming.mentions_bot)
        self.assertFalse(incoming.author_is_bot)

    async def test_plain_send_uses_channel_and_disables_mentions(self) -> None:
        source = FakeMessage()
        result = PipelineResult(True, "返事", "plain", 1, None)
        sent = await send_result(source, result)
        self.assertEqual(sent, "plain-sent")
        self.assertEqual(source.reply_calls, [])
        self.assertEqual(source.channel.calls[0][0], "返事")
        self.assertIn("allowed_mentions", source.channel.calls[0][1])
        self.assertNotIn("view", source.channel.calls[0][1])

    async def test_discord_reply_disables_mentions(self) -> None:
        source = FakeMessage()
        result = PipelineResult(True, "返事", "discord_reply", 1, "100")
        sent = await send_result(source, result)
        self.assertEqual(sent, "reply-sent")
        self.assertEqual(source.channel.calls, [])
        self.assertFalse(source.reply_calls[0][1]["mention_author"])
        self.assertIn("allowed_mentions", source.reply_calls[0][1])
        self.assertNotIn("view", source.reply_calls[0][1])

    async def test_ignored_intake_does_not_start_typing(self) -> None:
        class Pipeline:
            async def intake(self, incoming):
                return None

            async def process_turn(self, turn):
                raise AssertionError("ignored input must not be processed")

        source = FakeMessage()
        bot = SimpleNamespace(user=SimpleNamespace(id=99, display_name="ゆの"))
        runtime = ConversationRuntime(Pipeline(), TurnManager(TurnBuffer(0)))

        await handle_message(bot, source, runtime)

        self.assertEqual(source.channel.typing_enters, 0)

    async def test_directed_generation_uses_one_typing_context(self) -> None:
        class Pipeline:
            async def process_turn(self, turn):
                return PipelineResult(True, "返事", "plain", 1, None)

        source = FakeMessage()
        turn = PipelineTurn(
            stream_id=1,
            author_id="7",
            content="話そう",
            source_user_message_ids=(10,),
            should_reply=True,
            route_reason="dm",
            reply_mode="plain",
            reply_to_discord_message_id=None,
        )

        result = await process_turn_with_typing(source, Pipeline(), turn)

        self.assertTrue(result.should_send)
        self.assertEqual(source.channel.typing_enters, 1)
        self.assertEqual(source.channel.typing_exits, 1)

    async def test_typing_context_is_closed_after_generation_failure(self) -> None:
        class Pipeline:
            async def process_turn(self, turn):
                raise RuntimeError("generation failed")

        source = FakeMessage()
        turn = PipelineTurn(
            stream_id=1,
            author_id="7",
            content="hello",
            source_user_message_ids=(10,),
            should_reply=True,
            route_reason="dm",
            reply_mode="plain",
            reply_to_discord_message_id=None,
        )

        with self.assertRaises(RuntimeError):
            await process_turn_with_typing(source, Pipeline(), turn)

        self.assertEqual(source.channel.typing_enters, 1)
        self.assertEqual(source.channel.typing_exits, 1)

    async def test_typing_context_is_closed_after_cancellation(self) -> None:
        started = asyncio.Event()

        class Pipeline:
            async def process_turn(self, turn):
                started.set()
                await asyncio.Event().wait()

        source = FakeMessage()
        turn = PipelineTurn(
            stream_id=1,
            author_id="7",
            content="hello",
            source_user_message_ids=(10,),
            should_reply=True,
            route_reason="dm",
            reply_mode="plain",
            reply_to_discord_message_id=None,
        )
        task = asyncio.create_task(process_turn_with_typing(source, Pipeline(), turn))
        await started.wait()
        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertEqual(source.channel.typing_enters, 1)
        self.assertEqual(source.channel.typing_exits, 1)

    async def test_assistant_is_saved_before_post_send_observation(self) -> None:
        class Pipeline:
            def __init__(self):
                self.calls = []

            async def record_sent_assistant(self, result, sent):
                self.calls.append("saved")

            async def observe_after_send(self, ticket):
                self.calls.append("observed")

        pipeline = Pipeline()
        result = PipelineResult(True, "返事", "plain", 1, None)
        from yuno.messages import SentMessage
        await finalize_sent_message(
            pipeline, result, SentMessage("2", "99", "ゆの", "返事", "now")
        )
        self.assertEqual(pipeline.calls, ["saved", "observed"])

    async def test_observation_failure_does_not_undo_assistant_save(self) -> None:
        class Pipeline:
            def __init__(self):
                self.saved = False

            async def record_sent_assistant(self, result, sent):
                self.saved = True

            async def observe_after_send(self, ticket):
                raise RuntimeError("care failed")

        pipeline = Pipeline()
        result = PipelineResult(True, "返事", "plain", 1, None)
        from yuno.messages import SentMessage
        await finalize_sent_message(
            pipeline, result, SentMessage("2", "99", "ゆの", "返事", "now")
        )
        self.assertTrue(pipeline.saved)

    async def test_assistant_save_failure_skips_observation(self) -> None:
        class Pipeline:
            def __init__(self):
                self.observed = False

            async def record_sent_assistant(self, result, sent):
                raise RuntimeError("save failed")

            async def observe_after_send(self, ticket):
                self.observed = True

        pipeline = Pipeline()
        result = PipelineResult(True, "返事", "plain", 1, None)
        from yuno.messages import SentMessage
        await finalize_sent_message(
            pipeline, result, SentMessage("2", "99", "ゆの", "返事", "now")
        )
        self.assertFalse(pipeline.observed)

    async def test_compatible_message_supersedes_in_flight_reply(self) -> None:
        generation_started = asyncio.Event()
        release_generation = asyncio.Event()

        class Pipeline:
            def __init__(self):
                self.stored = []
                self.generated = []
                self.saved = []

            async def intake(self, incoming):
                self.stored.append(incoming.discord_message_id)
                directed = incoming.discord_message_id == "100"
                return PipelineTurn(
                    stream_id=1,
                    author_id=incoming.author_id,
                    content=incoming.raw_content,
                    source_user_message_ids=(
                        10 if directed else 11,
                    ),
                    should_reply=directed,
                    route_reason="mention" if directed else "listening_only",
                    reply_mode="discord_reply" if directed else "none",
                    reply_to_discord_message_id=(
                        incoming.discord_message_id if directed else None
                    ),
                )

            async def process_turn(self, turn):
                self.generated.append(turn)
                if len(turn.source_user_message_ids) == 1:
                    generation_started.set()
                    await release_generation.wait()
                    text = "古い返事"
                else:
                    text = "まとめた返事"
                return PipelineResult(
                    True,
                    text,
                    turn.reply_mode,
                    turn.stream_id,
                    turn.reply_to_discord_message_id,
                )

            async def record_sent_assistant(self, result, sent):
                self.saved.append((result.reply_text, sent.content))

            async def observe_after_send(self, ticket):
                return None

        class Reactions:
            async def add_for_marks(self, source, marks):
                return None

        class Sent:
            def __init__(self, content):
                self.id = 900
                self.content = content
                self.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

        class RuntimeMessage(FakeMessage):
            def __init__(self, message_id, content, channel):
                super().__init__()
                self.id = message_id
                self.content = content
                self.channel = channel
                self.reference = None

            async def reply(self, content, **kwargs):
                self.reply_calls.append((content, kwargs))
                return Sent(content)

        pipeline = Pipeline()
        runtime = ConversationRuntime(
            pipeline,
            TurnManager(TurnBuffer(0)),
            Reactions(),
        )
        bot = SimpleNamespace(user=SimpleNamespace(id=99, display_name="ゆの"))
        channel = FakeChannel()
        first = RuntimeMessage(100, "ゆの", channel)
        second = RuntimeMessage(101, "どこにいる？", channel)

        with self.assertLogs("yuno.discord.events", level="INFO") as captured:
            first_task = asyncio.create_task(handle_message(bot, first, runtime))
            await generation_started.wait()
            await handle_message(bot, second, runtime)
            release_generation.set()
            await first_task

        timing_logs = "\n".join(captured.output)
        self.assertIn("timing intake", timing_logs)
        self.assertIn("timing turn_selection", timing_logs)
        self.assertIn("timing stale_generation", timing_logs)
        self.assertIn("timing discord_send", timing_logs)
        self.assertIn("timing post_send_observation", timing_logs)
        self.assertNotIn(first.content, timing_logs)
        self.assertNotIn(second.content, timing_logs)

        self.assertEqual(pipeline.stored, ["100", "101"])
        self.assertEqual(
            [turn.content for turn in pipeline.generated],
            ["ゆの", "ゆの\nどこにいる？"],
        )
        self.assertEqual(
            pipeline.generated[-1].source_user_message_ids,
            (10, 11),
        )
        self.assertEqual([call[0] for call in first.reply_calls], ["まとめた返事"])
        self.assertEqual(second.reply_calls, [])
        self.assertEqual(pipeline.saved, [("まとめた返事", "まとめた返事")])
        self.assertNotIn("view", first.reply_calls[0][1])
