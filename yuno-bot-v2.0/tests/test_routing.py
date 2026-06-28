from pathlib import Path
from types import SimpleNamespace
import unittest

from yuno.config import Settings
from yuno.discord.routing import route_message


def settings(*channel_ids: int) -> Settings:
    return Settings(
        discord_token="",
        discord_client_id=None,
        openai_api_key="",
        openai_model="",
        database_file=Path("unused.sqlite3"),
        listening_channel_ids=frozenset(channel_ids),
        log_level="INFO",
    )


class RoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bot_user = SimpleNamespace(id=99)

    def message(self, content: str, channel_id: int, guild_id=1, mentions=None):
        return SimpleNamespace(
            content=content,
            channel=SimpleNamespace(id=channel_id),
            guild=None if guild_id is None else SimpleNamespace(id=guild_id),
            mentions=mentions or [],
        )

    def test_listening_channel_is_stored_without_automatic_reply(self) -> None:
        route = route_message(self.message("近くの会話", 10), self.bot_user, settings(10))
        self.assertTrue(route.should_store)
        self.assertFalse(route.should_reply)

    def test_unlisted_nonmention_is_not_stored(self) -> None:
        route = route_message(self.message("遠くの会話", 20), self.bot_user, settings(10))
        self.assertFalse(route.should_store)
        self.assertFalse(route.should_reply)

    def test_mention_is_cleaned_and_replied_to(self) -> None:
        route = route_message(
            self.message("<@99> おはよう", 20, mentions=[self.bot_user]),
            self.bot_user,
            settings(),
        )
        self.assertTrue(route.should_store)
        self.assertTrue(route.should_reply)
        self.assertEqual(route.clean_content, "おはよう")

    def test_dm_is_stored_and_replied_to(self) -> None:
        route = route_message(self.message("ひみつ", 30, guild_id=None), self.bot_user, settings())
        self.assertTrue(route.should_store)
        self.assertTrue(route.should_reply)
