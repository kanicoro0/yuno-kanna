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

        self.assertTrue(result.wants_to_speak)
        self.assertTrue(result.should_speak)
        self.assertEqual(result.reply_reason, "followup")
        self.assertEqual(result.speaker_note, "answer briefly")

    def test_parse_rejects_unknown_reply_reason(self) -> None:
        result = parse_care_result({
            "should_speak": True,
            "reply_reason": "unknown",
        })

        self.assertEqual(result.reply_reason, "")


if __name__ == "__main__":
    unittest.main()
