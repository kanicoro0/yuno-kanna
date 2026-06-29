from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from yuno.discord.events import finalize_sent_message, send_result
from yuno.discord.input import to_incoming_message
from yuno.pipeline import PipelineResult


class FakeChannel:
    def __init__(self):
        self.id = 10
        self.calls = []

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

    async def test_discord_reply_disables_mentions(self) -> None:
        source = FakeMessage()
        result = PipelineResult(True, "返事", "discord_reply", 1, "100")
        sent = await send_result(source, result)
        self.assertEqual(sent, "reply-sent")
        self.assertEqual(source.channel.calls, [])
        self.assertFalse(source.reply_calls[0][1]["mention_author"])
        self.assertIn("allowed_mentions", source.reply_calls[0][1])

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
