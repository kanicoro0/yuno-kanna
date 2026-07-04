import asyncio
import unittest

from yuno.turns import PipelineTurn, TurnBuffer


def make_turn(
    message_id: int,
    content: str,
    *,
    stream_id: int = 1,
    author_id: str = "7",
    reply_target=None,
) -> PipelineTurn:
    return PipelineTurn(
        stream_id=stream_id,
        author_id=author_id,
        content=content,
        source_user_message_ids=(message_id,),
        should_reply=True,
        route_reason="dm",
        reply_mode="plain",
        reply_to_discord_message_id=reply_target,
    )


class PipelineTurnTests(unittest.TestCase):
    def test_source_record_ids_can_represent_a_future_combined_turn(self) -> None:
        turn = PipelineTurn(
            stream_id=1,
            author_id="7",
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
        self.assertEqual(turn.care_source_user_message_id, 11)


class TurnBufferTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.buffer = TurnBuffer(debounce_seconds=0.01)

    async def test_single_turn_is_returned_unchanged(self) -> None:
        original = make_turn(10, "only")

        selected = await self.buffer.push(original)

        self.assertIs(selected, original)

    async def test_same_author_and_stream_are_combined(self) -> None:
        first, second = await asyncio.gather(
            self.buffer.push(make_turn(10, "first")),
            self.buffer.push(make_turn(11, "second")),
        )

        selected = first or second
        self.assertEqual(selected.content, "first\nsecond")
        self.assertEqual(selected.source_user_message_ids, (10, 11))
        self.assertEqual(sum(item is not None for item in (first, second)), 1)

    async def test_different_authors_are_not_combined(self) -> None:
        results = await asyncio.gather(
            self.buffer.push(make_turn(10, "first", author_id="7")),
            self.buffer.push(make_turn(11, "second", author_id="8")),
        )

        self.assertEqual(
            {item.source_user_message_ids for item in results}, {(10,), (11,)}
        )

    async def test_different_streams_are_not_combined(self) -> None:
        results = await asyncio.gather(
            self.buffer.push(make_turn(10, "first", stream_id=1)),
            self.buffer.push(make_turn(11, "second", stream_id=2)),
        )

        self.assertEqual({item.stream_id for item in results}, {1, 2})

    async def test_reply_target_changes_prevent_merging(self) -> None:
        results = await asyncio.gather(
            self.buffer.push(make_turn(10, "first", reply_target="a")),
            self.buffer.push(make_turn(11, "second", reply_target="b")),
        )

        self.assertEqual(
            {item.source_user_message_ids for item in results}, {(10,), (11,)}
        )


if __name__ == "__main__":
    unittest.main()
