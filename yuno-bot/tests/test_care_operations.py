import unittest

from yuno.care.operations import PendingCareOperations


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


if __name__ == '__main__':
    unittest.main()
