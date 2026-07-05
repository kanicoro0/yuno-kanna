import asyncio
import unittest

from yuno.turns import PipelineTurn, TurnBuffer, TurnManager, TurnPhase


def make_turn(
    message_id: int,
    content: str,
    *,
    stream_id: int = 1,
    author_id: str = "7",
    reply_target=None,
    should_reply: bool = True,
    route_reason: str = "dm",
    reply_mode: str = "plain",
) -> PipelineTurn:
    return PipelineTurn(
        stream_id=stream_id,
        author_id=author_id,
        content=content,
        source_user_message_ids=(message_id,),
        should_reply=should_reply,
        route_reason=route_reason,
        reply_mode=reply_mode,
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

    async def test_directed_turn_absorbs_same_author_listening_followup(self) -> None:
        directed = make_turn(
            10,
            "consider this",
            reply_target="discord-1",
            should_reply=True,
            route_reason="mention",
            reply_mode="discord_reply",
        )
        followup = make_turn(
            11,
            "additional detail",
            should_reply=False,
            route_reason="listening_only",
            reply_mode="none",
        )

        first, second = await asyncio.gather(
            self.buffer.push(directed),
            self.buffer.push(followup),
        )

        selected = first or second
        self.assertEqual(selected.content, "consider this\nadditional detail")
        self.assertEqual(selected.source_user_message_ids, (10, 11))
        self.assertTrue(selected.should_reply)
        self.assertEqual(selected.route_reason, "mention")
        self.assertEqual(selected.reply_mode, "discord_reply")
        self.assertEqual(
            selected.reply_to_discord_message_id, "discord-1"
        )
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


class TurnManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.manager = TurnManager(TurnBuffer(debounce_seconds=0.01))

    async def test_buffering_messages_can_still_merge(self) -> None:
        first, second = await asyncio.gather(
            self.manager.select(make_turn(10, "first")),
            self.manager.select(make_turn(11, "second")),
        )

        selected = first or second
        self.assertEqual(selected.source_user_message_ids, (10, 11))
        self.assertEqual(self.manager.phase_for(1), TurnPhase.BUFFERING)

        async with self.manager.processing(selected):
            self.assertEqual(self.manager.phase_for(1), TurnPhase.GENERATING)

        self.assertEqual(self.manager.phase_for(1), TurnPhase.IDLE)

    async def test_compatible_turn_during_generation_supersedes_active(self) -> None:
        first = await self.manager.select(make_turn(10, "first"))

        async with self.manager.processing(first):
            initial = self.manager.current_generation(1)
            selected = await self.manager.select(make_turn(11, "second"))
            latest = self.manager.current_generation(1)

            self.assertIsNone(selected)
            self.assertFalse(self.manager.is_current(initial))
            self.assertTrue(self.manager.is_current(latest))
            self.assertEqual(latest.turn.content, "first\nsecond")
            self.assertEqual(latest.turn.source_user_message_ids, (10, 11))

        self.assertEqual(self.manager.phase_for(1), TurnPhase.IDLE)

    async def test_different_author_during_generation_waits_for_current(self) -> None:
        first = await self.manager.select(make_turn(10, "first"))
        first_entered = asyncio.Event()
        release_first = asyncio.Event()
        second_entered = asyncio.Event()
        active = 0
        maximum_active = 0

        async def process_first() -> None:
            nonlocal active, maximum_active
            async with self.manager.processing(first):
                active += 1
                maximum_active = max(maximum_active, active)
                first_entered.set()
                await release_first.wait()
                self.manager.mark_sending(1)
                active -= 1

        async def process_second() -> None:
            nonlocal active, maximum_active
            selected = await self.manager.select(
                make_turn(11, "second", author_id="8")
            )
            async with self.manager.processing(selected):
                active += 1
                maximum_active = max(maximum_active, active)
                second_entered.set()
                active -= 1

        first_task = asyncio.create_task(process_first())
        await first_entered.wait()
        second_task = asyncio.create_task(process_second())
        await asyncio.sleep(0.02)

        self.assertFalse(second_entered.is_set())
        self.assertEqual(self.manager.phase_for(1), TurnPhase.GENERATING)

        release_first.set()
        await asyncio.gather(first_task, second_task)

        self.assertEqual(maximum_active, 1)
        self.assertTrue(second_entered.is_set())
        self.assertEqual(self.manager.phase_for(1), TurnPhase.IDLE)

    async def test_incompatible_reply_target_is_not_absorbed(self) -> None:
        first = await self.manager.select(
            make_turn(10, "first", reply_target="a")
        )

        async with self.manager.processing(first):
            initial = self.manager.current_generation(1)
            second = await self.manager.select(
                make_turn(11, "second", reply_target="b")
            )

            self.assertEqual(second.source_user_message_ids, (11,))
            self.assertTrue(self.manager.is_current(initial))
            self.assertEqual(
                self.manager.current_generation(1).turn.source_user_message_ids,
                (10,),
            )

        async with self.manager.processing(second):
            self.assertEqual(
                self.manager.current_generation(1).turn.source_user_message_ids,
                (11,),
            )

        self.assertEqual(self.manager.phase_for(1), TurnPhase.IDLE)

    async def test_generation_failure_returns_stream_to_idle(self) -> None:
        selected = await self.manager.select(make_turn(10, "first"))

        with self.assertRaises(RuntimeError):
            async with self.manager.processing(selected):
                raise RuntimeError("generation failed")

        self.assertEqual(self.manager.phase_for(1), TurnPhase.IDLE)

    async def test_two_sends_in_one_stream_do_not_overlap(self) -> None:
        first = await self.manager.select(make_turn(10, "first"))
        second = await self.manager.select(make_turn(11, "second"))
        first_sending = asyncio.Event()
        release_first = asyncio.Event()
        active_sends = 0
        maximum_active_sends = 0

        async def send(selected, *, wait: bool) -> None:
            nonlocal active_sends, maximum_active_sends
            async with self.manager.processing(selected):
                self.manager.mark_sending(1)
                active_sends += 1
                maximum_active_sends = max(maximum_active_sends, active_sends)
                if wait:
                    first_sending.set()
                    await release_first.wait()
                active_sends -= 1

        first_task = asyncio.create_task(send(first, wait=True))
        await first_sending.wait()
        second_task = asyncio.create_task(send(second, wait=False))
        await asyncio.sleep(0)

        self.assertEqual(self.manager.phase_for(1), TurnPhase.SENDING)
        self.assertFalse(second_task.done())

        release_first.set()
        await asyncio.gather(first_task, second_task)

        self.assertEqual(maximum_active_sends, 1)
        self.assertEqual(self.manager.phase_for(1), TurnPhase.IDLE)

if __name__ == "__main__":
    unittest.main()
