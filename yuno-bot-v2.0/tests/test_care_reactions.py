import logging
import unittest

from yuno.care_marks.models import CareMark
from yuno.discord.care_reactions import (
    CareReactionSurface,
    pick_care_mark_reaction,
)


def mark(kind: str, status: str, text: str = '残しておくこと') -> CareMark:
    return CareMark(
        id=1,
        public_id='care_0001',
        stream_id=1,
        source_message_id=1,
        kind=kind,
        status=status,
        text=text,
        created_at='now',
        updated_at='now',
    )


class FakeMessage:
    def __init__(self, content: str = 'ここに置いておいて'):
        self.content = content
        self.reactions = []

    async def add_reaction(self, emoji: str) -> None:
        self.reactions.append(emoji)


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

    async def test_hidden_closed_and_draft_marks_do_not_react(self) -> None:
        message = FakeMessage()

        await CareReactionSurface().add_for_marks(message, (
            mark('memory', 'hidden'),
            mark('memory', 'draft'),
            mark('attention', 'closed'),
            mark('attention', 'hidden'),
        ))

        self.assertEqual(message.reactions, [])

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
