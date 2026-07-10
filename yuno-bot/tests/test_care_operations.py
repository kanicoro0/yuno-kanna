import unittest

from yuno.care.models import CareReadResult
from yuno.care.operations import (
    PendingCareOperations,
    ask_back_reply,
    care_operations_log_line,
    requests_restore,
)
from yuno.care.service import CareApplication


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


class PendingCareOperationsTests(unittest.TestCase):
    def test_pending_operation_waits_for_the_same_speaker(self) -> None:
        pending = PendingCareOperations(clock=FakeClock())
        pending.set(1, '7', 'forget')

        self.assertEqual(pending.peek(1, '7'), 'forget')
        self.assertEqual(pending.peek(1, '7'), 'forget')

    def test_other_speakers_do_not_see_or_disturb_it(self) -> None:
        pending = PendingCareOperations(clock=FakeClock())
        pending.set(1, '7', 'close')

        self.assertIsNone(pending.peek(1, '8'))
        self.assertEqual(pending.peek(1, '7'), 'close')

    def test_pending_operation_expires_quietly(self) -> None:
        clock = FakeClock()
        pending = PendingCareOperations(ttl_seconds=300.0, clock=clock)
        pending.set(1, '7', 'forget')

        clock.now = 299.0
        self.assertEqual(pending.peek(1, '7'), 'forget')
        clock.now = 300.0
        self.assertIsNone(pending.peek(1, '7'))

    def test_clear_removes_the_pending_operation(self) -> None:
        pending = PendingCareOperations(clock=FakeClock())
        pending.set(1, '7', 'promote')
        pending.clear(1)

        self.assertIsNone(pending.peek(1, '7'))

    def test_unknown_operations_are_not_stored(self) -> None:
        pending = PendingCareOperations(clock=FakeClock())
        pending.set(1, '7', 'reset')

        self.assertIsNone(pending.peek(1, '7'))

    def test_streams_are_independent(self) -> None:
        pending = PendingCareOperations(clock=FakeClock())
        pending.set(1, '7', 'forget')
        pending.set(2, '7', 'close')

        self.assertEqual(pending.peek(1, '7'), 'forget')
        self.assertEqual(pending.peek(2, '7'), 'close')


class AskBackReplyTests(unittest.TestCase):
    def test_reply_is_deterministic_for_the_same_turn(self) -> None:
        first = ask_back_reply('forget', 'あれはもう忘れて')
        second = ask_back_reply('forget', 'あれはもう忘れて')

        self.assertEqual(first, second)

    def test_every_reply_is_a_short_question(self) -> None:
        seeds = [f'ため書き{index}' for index in range(12)]
        for operation in ('forget', 'close', 'promote'):
            for seed in seeds:
                reply = ask_back_reply(operation, seed)
                with self.subTest(operation=operation, reply=reply):
                    self.assertIn('？', reply)
                    self.assertLess(len(reply), 40)

    def test_replies_never_leak_internal_words(self) -> None:
        for operation in ('forget', 'close', 'promote'):
            for index in range(8):
                reply = ask_back_reply(operation, f'seed{index}').casefold()
                for word in (
                    'caremark', 'care_', 'status', 'memory', 'attention',
                    'draft', 'active', 'hidden', 'pending', 'unclear',
                ):
                    self.assertNotIn(word, reply)

    def test_wording_varies_across_seeds(self) -> None:
        replies = {
            ask_back_reply('forget', f'話{index}') for index in range(24)
        }
        self.assertGreater(len(replies), 1)


class RequestsRestoreTests(unittest.TestCase):
    def test_memory_explicit_restore_is_detected(self) -> None:
        for content in (
            'さっきの記憶、戻して',
            '忘れたやつを戻してほしい',
            '覚えてたこと、復活できる？',
        ):
            with self.subTest(content=content):
                self.assertTrue(requests_restore(content))

    def test_plain_restore_words_do_not_match(self) -> None:
        for content in (
            '椅子を元の場所に戻しておいて',
            'ゲームのセーブを復活させたい',
            '記憶力がほしい',
        ):
            with self.subTest(content=content):
                self.assertFalse(requests_restore(content))


class CareOperationsLogLineTests(unittest.TestCase):
    def line(self, **overrides):
        arguments = dict(
            route_reason='mention',
            spoke=True,
            source_content='今日は晴れだね',
            result=CareReadResult(),
            application=CareApplication(),
            pending_operation='',
        )
        arguments.update(overrides)
        return care_operations_log_line(**arguments)

    def test_plain_turn_renders_all_fields_with_none(self) -> None:
        line = self.line()

        self.assertIn('route=mention', line)
        self.assertIn('spoke=true', line)
        self.assertIn('lexical_request_hit=none', line)
        self.assertIn('proposed=close:0,forget:0,promote:0', line)
        self.assertIn(
            'applied=created:0,touched:0,closed:0,forgotten:0,promoted:0',
            line,
        )
        self.assertIn('blocked=none', line)
        self.assertIn('unclear=none', line)
        self.assertIn('pending=none', line)
        self.assertIn('pending_outcome=none', line)

    def test_message_text_never_appears_in_the_line(self) -> None:
        secret = '通院のことは忘れてほしい'
        line = self.line(source_content=secret)

        self.assertNotIn('通院', line)
        self.assertIn('lexical_request_hit=forget', line)

    def test_counts_hits_proposals_and_applications(self) -> None:
        line = self.line(
            source_content='これ覚えて、あの話はもう閉じて',
            result=CareReadResult(
                close_care_mark_ids=('care_1', 'care_2'),
                forget_care_mark_ids=('care_3',),
            ),
            application=CareApplication(
                created_care_mark_ids=('care_9',),
                closed_care_mark_ids=('care_1',),
            ),
        )

        self.assertIn('lexical_request_hit=remember,close', line)
        self.assertIn('proposed=close:2,forget:1,promote:0', line)
        self.assertIn(
            'applied=created:1,touched:0,closed:1,forgotten:0,promoted:0',
            line,
        )

    def test_blocked_counts_render_per_operation_and_reason(self) -> None:
        line = self.line(
            application=CareApplication(blocked_operations=(
                ('close', 'target', 2),
                ('forget', 'gate', 1),
                ('promote', 'sensitive', 1),
            )),
        )

        self.assertIn(
            'blocked=close:target:2,forget:gate:1,promote:sensitive:1', line
        )

    def test_pending_outcome_applied(self) -> None:
        line = self.line(
            pending_operation='forget',
            application=CareApplication(
                forgotten_care_mark_ids=('care_1',),
            ),
        )

        self.assertIn('pending=forget', line)
        self.assertIn('pending_outcome=applied', line)

    def test_pending_outcome_re_asked(self) -> None:
        line = self.line(
            pending_operation='forget',
            result=CareReadResult(unclear_operation='forget'),
        )

        self.assertIn('pending_outcome=re_asked', line)

    def test_pending_outcome_no_action_makes_no_further_claim(self) -> None:
        line = self.line(pending_operation='forget')

        self.assertIn('pending_outcome=no_action', line)
        self.assertNotIn('unrelated', line)


if __name__ == '__main__':
    unittest.main()
