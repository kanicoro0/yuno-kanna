import unittest

from yuno.care.reader import parse_care_result


class CareReaderTests(unittest.TestCase):
    def test_parse_reply_decision_fields(self) -> None:
        result = parse_care_result({
            "wants_to_speak": True,
            "should_speak": True,
            "reply_reason": "followup",
            "speaker_note": "answer briefly",
            "care_mark_candidates": [],
            "read_cue_updates": [],
        })

        self.assertTrue(result.decision_made)
        self.assertTrue(result.wants_to_speak)
        self.assertTrue(result.should_speak)
        self.assertEqual(result.reply_reason, "followup")
        self.assertEqual(result.speaker_note, "answer briefly")

    def test_parse_false_should_speak_is_still_a_decision(self) -> None:
        result = parse_care_result({
            "should_speak": False,
            "reply_reason": "none",
        })

        self.assertTrue(result.decision_made)
        self.assertFalse(result.should_speak)

    def test_parse_without_should_speak_has_no_decision(self) -> None:
        result = parse_care_result({
            "reply_reason": "followup",
        })

        self.assertFalse(result.decision_made)

    def test_parse_rejects_unknown_reply_reason(self) -> None:
        result = parse_care_result({
            "should_speak": True,
            "reply_reason": "unknown",
        })

        self.assertEqual(result.reply_reason, "")

    def test_parse_state_change_id_lists(self) -> None:
        result = parse_care_result({
            "close_care_mark_ids": ["care_0001", "not-a-care-id", "care_0001"],
            "forget_care_mark_ids": ["care_0002"],
            "promote_care_mark_ids": ["care_0003", 7],
        })

        self.assertEqual(result.close_care_mark_ids, ("care_0001",))
        self.assertEqual(result.forget_care_mark_ids, ("care_0002",))
        self.assertEqual(result.promote_care_mark_ids, ("care_0003",))

    def test_parse_missing_state_change_lists_stay_empty(self) -> None:
        result = parse_care_result({"should_speak": True})

        self.assertEqual(result.close_care_mark_ids, ())
        self.assertEqual(result.forget_care_mark_ids, ())
        self.assertEqual(result.promote_care_mark_ids, ())


if __name__ == "__main__":
    unittest.main()
