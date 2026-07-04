import unittest

from yuno.turns import PipelineTurn


class PipelineTurnTests(unittest.TestCase):
    def test_source_record_ids_can_represent_a_future_combined_turn(self) -> None:
        turn = PipelineTurn(
            stream_id=1,
            content="first\nsecond",
            source_user_message_ids=(10, 11),
            should_reply=True,
            route_reason="mention",
            reply_mode="discord_reply",
            reply_to_discord_message_id="discord-2",
        )

        self.assertEqual(turn.source_user_message_ids, (10, 11))
        with self.assertRaises(ValueError):
            _ = turn.single_source_user_message_id


if __name__ == "__main__":
    unittest.main()
