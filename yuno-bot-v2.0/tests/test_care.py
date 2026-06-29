import unittest

from yuno.care.models import CareReadRequest, CareReadResult
from yuno.care.reader import CareReader, parse_care_result


class FakeJsonClient:
    def __init__(self, value):
        self.value = value
        self.messages = None

    async def complete_json(self, messages):
        self.messages = messages
        return self.value


class CareReaderTests(unittest.IsolatedAsyncioTestCase):
    def request(self) -> CareReadRequest:
        return CareReadRequest(
            current_message="いまの発言",
            recent_messages=({"role": "user", "content": "A: 前の発言"},),
            memory_marks=(),
            attention_items=(),
            interest_terms=(),
            addressing_strength=1.0,
            interest_salience=0.0,
        )

    async def test_reader_parses_json_without_control_values_in_request(self) -> None:
        client = FakeJsonClient({
            "wants_to_speak": True,
            "should_speak": True,
            "memory_candidates": [{
                "content": "残す印", "kind": "pin", "status": "active", "confidence": 0.8,
            }],
            "attention_candidates": [{"text": "開いた問い", "rank": 0.7}],
            "interest_updates": [{"term": "星", "weight": 0.4}],
            "include_memory_ids": ["mem_0001"],
            "include_attention_ids": ["att_0001"],
        })
        result = await CareReader(client).read(self.request())
        self.assertTrue(result.should_speak)
        self.assertEqual(result.memory_candidates[0].content, "残す印")
        payload = client.messages[1]["content"]
        self.assertNotIn("reply_mode", payload)
        self.assertNotIn("routing", payload)
        self.assertNotIn("reason", payload)

    async def test_invalid_parse_falls_back_to_empty_result(self) -> None:
        result = await CareReader(FakeJsonClient("not an object")).read(self.request())
        self.assertEqual(result, CareReadResult())

    def test_limits_lengths_numbers_and_invalid_values(self) -> None:
        result = parse_care_result({
            "memory_candidates": [
                {"content": "x" * 600, "kind": "pin", "status": "active", "confidence": 4},
                {"content": "ok", "kind": "correction", "status": "pending", "confidence": -1},
                {"content": "bad kind", "kind": "mood", "status": "active"},
                {"content": "fourth", "kind": "pin", "status": "active"},
            ],
            "attention_candidates": [
                {"text": f"attention-{index}" + "a" * 500, "rank": 2}
                for index in range(5)
            ],
            "interest_updates": [
                {"term": f"term-{index}" + "b" * 100, "weight": 2}
                for index in range(8)
            ],
            "include_memory_ids": [f"mem_{index:04d}" for index in range(20)],
            "include_attention_ids": [f"att_{index:04d}" for index in range(20)],
        })
        self.assertEqual(len(result.memory_candidates), 2)
        self.assertEqual(len(result.memory_candidates[0].content), 500)
        self.assertEqual(result.memory_candidates[0].confidence, 1.0)
        self.assertEqual(result.memory_candidates[1].confidence, 0.0)
        self.assertEqual(len(result.attention_candidates), 3)
        self.assertTrue(all(len(item.text) <= 400 for item in result.attention_candidates))
        self.assertEqual(len(result.interest_updates), 5)
        self.assertTrue(all(len(item.term) <= 80 for item in result.interest_updates))
        self.assertEqual(len(result.include_memory_ids), 8)
        self.assertEqual(len(result.include_attention_ids), 8)

    def test_sensitive_or_other_person_active_candidate_becomes_pending(self) -> None:
        result = parse_care_result({
            "memory_candidates": [
                {"content": "通院している", "kind": "pin", "status": "active"},
                {
                    "content": "友人についての話", "kind": "pin", "status": "active",
                    "about_other_person": True,
                },
                {
                    "content": "センシティブ", "kind": "pin", "status": "active",
                    "sensitive": True,
                },
            ]
        })
        self.assertEqual(
            [item.status for item in result.memory_candidates],
            ["pending", "pending", "pending"],
        )

    def test_string_booleans_do_not_enable_speaking(self) -> None:
        result = parse_care_result({
            "wants_to_speak": "false",
            "should_speak": "true",
        })
        self.assertFalse(result.wants_to_speak)
        self.assertFalse(result.should_speak)
