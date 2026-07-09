import logging
from types import SimpleNamespace
import unittest

from yuno.care_marks.models import CareMark
from yuno.discord.care_reactions import (
    CareReactionSurface,
    CareReactionTargetResolver,
    pick_care_mark_reaction,
)


def mark(
    kind: str,
    status: str,
    text: str = '残しておくこと',
    *,
    mark_id: int = 1,
    source_message_id: int = 1,
) -> CareMark:
    return CareMark(
        id=mark_id,
        public_id=f'care_{mark_id:04d}',
        stream_id=1,
        source_message_id=source_message_id,
        kind=kind,
        status=status,
        text=text,
        created_at='now',
        updated_at='now',
    )


class FakeChannel:
    def __init__(self):
        self.messages = {}
        self.fail_fetch = False

    async def fetch_message(self, message_id):
        if self.fail_fetch or message_id not in self.messages:
            raise RuntimeError('message unavailable')
        return self.messages[message_id]


class FakeMessage:
    def __init__(
        self,
        content: str = 'ここに置いておいて',
        *,
        message_id: int = 100,
        channel=None,
    ):
        self.content = content
        self.id = message_id
        self.channel = channel or FakeChannel()
        self.reactions = []

    async def add_reaction(self, emoji: str) -> None:
        self.reactions.append(emoji)


class FakeConversations:
    def __init__(self, records):
        self.records = records

    async def get_message(self, message_id):
        return self.records.get(message_id)


class CareReactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_mark_can_receive_a_yuno_like_reaction(self) -> None:
        message = FakeMessage()

        await CareReactionSurface().add_for_marks(
            message, (mark('memory', 'active'),)
        )

        self.assertEqual(len(message.reactions), 1)
        self.assertTrue(message.reactions[0].strip())

    async def test_attention_mark_can_receive_a_yuno_like_reaction(self) -> None:
        message = FakeMessage('この話はまだ続きそう')

        await CareReactionSurface().add_for_marks(
            message, (mark('attention', 'open', '続きの話'),)
        )

        self.assertEqual(len(message.reactions), 1)

    async def test_draft_marks_do_not_react(self) -> None:
        message = FakeMessage()

        await CareReactionSurface().add_for_marks(message, (
            mark('memory', 'draft'),
        ))

        self.assertEqual(message.reactions, [])

    async def test_settled_marks_react_once_on_the_current_message(self) -> None:
        channel = FakeChannel()
        old_source = FakeMessage('前の内容', message_id=101, channel=channel)
        channel.messages = {101: old_source}
        request = FakeMessage(
            'さっきのは忘れて', message_id=100, channel=channel
        )
        conversations = FakeConversations({
            10: SimpleNamespace(stream_id=1, discord_message_id='101'),
        })
        surface = CareReactionSurface(
            CareReactionTargetResolver(conversations)
        )

        await surface.add_for_marks(request, (
            mark('memory', 'hidden', mark_id=1, source_message_id=10),
            mark('attention', 'closed', mark_id=2, source_message_id=10),
        ))

        self.assertEqual(len(request.reactions), 1)
        self.assertEqual(old_source.reactions, [])

    async def test_standing_marks_win_over_settled_marks(self) -> None:
        message = FakeMessage('こう呼んでね')

        await CareReactionSurface().add_for_marks(message, (
            mark('memory', 'hidden', '古い呼び方', mark_id=1),
            mark('memory', 'active', '新しい呼び方', mark_id=2),
        ))

        self.assertEqual(len(message.reactions), 1)

    def test_settled_picker_uses_the_quiet_settled_pool(self) -> None:
        settled_choices = {
            pick_care_mark_reaction(
                mark('attention', 'closed', f'区切り {index}'),
                f'もう終わった話 {index}',
            )
            for index in range(24)
        }

        self.assertGreater(len(settled_choices), 1)
        self.assertNotIn(None, settled_choices)

    async def test_reaction_failure_is_isolated(self) -> None:
        class FailingMessage(FakeMessage):
            async def add_reaction(self, emoji: str) -> None:
                raise RuntimeError('Discord unavailable')

        with self.assertLogs(
            'yuno.discord.care_reactions', logging.ERROR
        ) as captured:
            await CareReactionSurface().add_for_marks(
                FailingMessage(), (mark('memory', 'active'),)
            )

        self.assertIn('persisted', captured.output[0])

    async def test_reaction_prefers_latest_mark_source_message(self) -> None:
        channel = FakeChannel()
        bare_call = FakeMessage('ゆの', message_id=100, channel=channel)
        earlier = FakeMessage('前の内容', message_id=101, channel=channel)
        later = FakeMessage(
            'かにころってよんで', message_id=102, channel=channel
        )
        channel.messages = {101: earlier, 102: later}
        conversations = FakeConversations({
            10: SimpleNamespace(stream_id=1, discord_message_id='101'),
            11: SimpleNamespace(stream_id=1, discord_message_id='102'),
        })
        surface = CareReactionSurface(
            CareReactionTargetResolver(conversations)
        )

        await surface.add_for_marks(bare_call, (
            mark('memory', 'active', mark_id=1, source_message_id=10),
            mark('memory', 'active', mark_id=2, source_message_id=11),
        ))

        self.assertEqual(bare_call.reactions, [])
        self.assertEqual(earlier.reactions, [])
        self.assertEqual(len(later.reactions), 1)

    async def test_unavailable_source_falls_back_to_original_message(self) -> None:
        channel = FakeChannel()
        channel.fail_fetch = True
        original = FakeMessage('ゆの', message_id=100, channel=channel)
        conversations = FakeConversations({
            11: SimpleNamespace(stream_id=1, discord_message_id='102'),
        })
        surface = CareReactionSurface(
            CareReactionTargetResolver(conversations)
        )

        await surface.add_for_marks(original, (
            mark('attention', 'open', mark_id=2, source_message_id=11),
        ))

        self.assertEqual(len(original.reactions), 1)

    def test_picker_varies_without_assigning_fixed_emoji_meanings(self) -> None:
        memory_choices = {
            pick_care_mark_reaction(
                mark('memory', 'active', f'断片 {index}'),
                f'そのときの言葉 {index}',
            )
            for index in range(24)
        }
        attention_choices = {
            pick_care_mark_reaction(
                mark('attention', 'open', f'続き {index}'),
                f'まだ話している {index}',
            )
            for index in range(24)
        }

        self.assertGreater(len(memory_choices), 1)
        self.assertGreater(len(attention_choices), 1)
        self.assertTrue(memory_choices & attention_choices)


if __name__ == '__main__':
    unittest.main()
