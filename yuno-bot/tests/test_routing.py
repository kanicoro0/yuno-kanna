from pathlib import Path
import unittest

from yuno.config import Settings
from yuno.discord.routing import MessageRouter, call_name_strength, contains_call_name
from yuno.messages import IncomingMessage


def settings(*channel_ids: int) -> Settings:
    return Settings(
        discord_token="",
        discord_client_id=None,
        openai_api_key="",
        openai_model="",
        database_file=Path("unused.sqlite3"),
        listening_channel_ids=frozenset(channel_ids),
        yuno_call_names=("ゆの", "唯乃", "yuno"),
        log_level="INFO",
    )


class FakeRepository:
    def __init__(self, assistant_ids=()):
        self.assistant_ids = set(assistant_ids)

    async def is_assistant_message(self, message_id):
        return message_id in self.assistant_ids


def incoming(
    content: str,
    channel_id: int = 10,
    guild_id="1",
    *,
    mention: bool = False,
    reply_to=None,
    author_is_bot: bool = False,
) -> IncomingMessage:
    return IncomingMessage(
        discord_message_id="100",
        discord_channel_id=str(channel_id),
        discord_guild_id=guild_id,
        stream_kind="dm" if guild_id is None else "channel",
        author_id="7",
        author_name="こはる",
        author_is_bot=author_is_bot,
        bot_user_id="99",
        mentions_bot=mention,
        raw_content=content,
        created_at="2026-01-01T00:00:00+00:00",
        reply_to_discord_message_id=reply_to,
    )


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def route(self, message, channel_ids=(), assistant_ids=()):
        router = MessageRouter(settings(*channel_ids), FakeRepository(assistant_ids))
        return await router.route(message)

    async def test_dm_is_plain(self) -> None:
        route = await self.route(incoming("dm", guild_id=None))
        self.assertEqual((route.should_store, route.should_reply), (True, True))
        self.assertEqual((route.reason, route.reply_mode), ("dm", "plain"))

    async def test_mention_is_clean_discord_reply(self) -> None:
        route = await self.route(incoming("<@99> hello", mention=True))
        self.assertEqual(route.speaker_content, "hello")
        self.assertEqual((route.reason, route.reply_mode), ("mention", "discord_reply"))

    async def test_bare_mention_becomes_only_yuno_name(self) -> None:
        route = await self.route(incoming("<@!99>", mention=True))
        self.assertEqual(route.speaker_content, "ゆの")

    async def test_reply_to_assistant_is_discord_reply(self) -> None:
        route = await self.route(
            incoming("continue", reply_to="assistant-1"),
            assistant_ids={"assistant-1"},
        )
        self.assertEqual((route.reason, route.reply_mode), ("reply_to_yuno", "discord_reply"))
        self.assertTrue(route.should_reply)

    async def test_reply_to_user_or_unknown_is_not_reply_to_yuno(self) -> None:
        user_reply = await self.route(
            incoming("reply to user", reply_to="user-1"), channel_ids={10}
        )
        missing_reply = await self.route(incoming("missing reply", reply_to="missing"))
        self.assertEqual(user_reply.reason, "listening_only")
        self.assertFalse(user_reply.should_reply)
        self.assertEqual(missing_reply.reason, "ignored")

    async def test_direct_call_names_reply_plain_only_in_listening_channel(self) -> None:
        for value in ("ゆの", "ゆの、聞いて", "ゆのちゃん", "ねえゆの", "ゆのおはよ", "yuno", "唯乃"):
            with self.subTest(value=value):
                route = await self.route(incoming(value), channel_ids={10})
                self.assertEqual((route.reason, route.reply_mode), ("name_call", "plain"))
                self.assertTrue(route.should_reply)
        outside = await self.route(incoming("ねえゆの"))
        self.assertEqual(outside.reason, "ignored")

    async def test_weak_name_matches_are_read_without_immediate_reply(self) -> None:
        for value in ("しょうゆの作り方", "ゆのかわいい", "ゆのって名前いいよね", "ゆの起きてる？"):
            with self.subTest(value=value):
                route = await self.route(incoming(value), channel_ids={10})
                self.assertTrue(route.should_store)
                self.assertFalse(route.should_reply)
                self.assertEqual((route.reason, route.reply_mode), ("name_seen", "none"))

    async def test_listening_normal_message_is_store_only(self) -> None:
        route = await self.route(incoming("nearby"), channel_ids={10})
        self.assertTrue(route.should_store)
        self.assertFalse(route.should_reply)
        self.assertEqual((route.reason, route.reply_mode), ("listening_only", "none"))

    async def test_unlisted_and_bot_messages_are_ignored(self) -> None:
        outside = await self.route(incoming("outside"), channel_ids={20})
        bot = await self.route(incoming("ゆの", author_is_bot=True), channel_ids={10})
        self.assertFalse(outside.should_store)
        self.assertFalse(bot.should_store)

    def test_call_name_strength_distinguishes_direct_and_weak_calls(self) -> None:
        self.assertEqual(call_name_strength("ゆの、おはよ", ("ゆの",)), "direct")
        self.assertEqual(call_name_strength("しょうゆの作り方", ("ゆの",)), "weak")
        self.assertEqual(call_name_strength("ゆのかわいい", ("ゆの",)), "weak")
        self.assertEqual(call_name_strength("ゆの起きてる？", ("ゆの",)), "weak")
        self.assertIsNone(call_name_strength("nearby", ("ゆの",)))

    def test_latin_call_name_does_not_match_longer_word(self) -> None:
        self.assertTrue(contains_call_name("hey yuno!", ("yuno",)))
        self.assertFalse(contains_call_name("yunomi", ("yuno",)))
