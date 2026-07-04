import unittest

from yuno.scope import ChannelScope, GlobalScope, GuildScope, ScopeKind, StreamScope


class ScopeModelTests(unittest.TestCase):
    def test_global_scope(self) -> None:
        scope = GlobalScope()

        self.assertEqual(scope.kind, ScopeKind.GLOBAL)
        self.assertEqual(scope.to_dict(), {"kind": "global"})

    def test_guild_scope_normalizes_discord_id(self) -> None:
        scope = GuildScope(123)

        self.assertEqual(scope.guild_id, "123")
        self.assertEqual(scope.to_dict(), {"kind": "guild", "guild_id": "123"})

    def test_channel_scope_normalizes_discord_id(self) -> None:
        scope = ChannelScope(456)

        self.assertEqual(scope.channel_id, "456")
        self.assertEqual(
            scope.to_dict(), {"kind": "channel", "channel_id": "456"}
        )

    def test_stream_scope(self) -> None:
        scope = StreamScope(7)

        self.assertEqual(scope.stream_id, 7)
        self.assertEqual(scope.to_dict(), {"kind": "stream", "stream_id": 7})

    def test_equal_values_compare_equal(self) -> None:
        self.assertEqual(GuildScope("123"), GuildScope(123))
        self.assertNotEqual(GuildScope("123"), GuildScope("456"))

    def test_empty_discord_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ChannelScope(" ")

    def test_invalid_stream_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            StreamScope(0)


if __name__ == "__main__":
    unittest.main()
