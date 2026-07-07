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
            current_message='いまの発言',
            recent_messages=({'role': 'user', 'content': 'A: 前の発言'},),
            care_marks=(),
            read_cues=(),
            addressing_strength=1.0,
            cue_salience=0.0,
            route_reason='mention',
            reply_mode='discord_reply',
        )

    async def test_reader_parses_contract_with_route_state_only(self) -> None:
        client = FakeJsonClient({
            'wants_to_speak': True,
            'should_speak': True,
            'care_mark_candidates': [{
                'kind': 'memory',
                'status': 'active',
                'text': '残す印',
                'confidence': 0.8,
            }],
            'read_cue_updates': [{
                'candidate_text': '残す印',
                'term': '星',
                'weight': 0.4,
            }],
            'touch_care_mark_ids': ['care_0001'],
            'include_care_mark_ids': ['care_0001'],
        })

        result = await CareReader(client).read(self.request())

        self.assertTrue(result.should_speak)
        self.assertEqual(result.care_mark_candidates[0].text, '残す印')
        self.assertEqual(result.read_cue_updates[0].term, '星')
        payload = client.messages[1]['content']
        self.assertIn('route_reason', payload)
        self.assertIn('reply_mode', payload)
        self.assertNotIn('reply_reason', payload)
        self.assertNotIn('speaker_note', payload)
        self.assertNotIn('CareReader', payload)

    async def test_invalid_parse_falls_back_to_empty_result(self) -> None:
        result = await CareReader(FakeJsonClient('not an object')).read(
            self.request()
        )
        self.assertEqual(result, CareReadResult())

    def test_invalid_kind_or_status_is_ignored(self) -> None:
        result = parse_care_result({
            'care_mark_candidates': [
                {'kind': 'mood', 'status': 'active', 'text': 'bad kind'},
                {'kind': 'memory', 'status': 'open', 'text': 'bad status'},
                {'kind': 'attention', 'status': 'draft', 'text': 'bad status'},
                {'kind': 'attention', 'status': 'open', 'text': 'valid'},
            ],
        })

        self.assertEqual(
            [item.text for item in result.care_mark_candidates],
            ['valid'],
        )

    def test_limits_lengths_numbers_and_ids(self) -> None:
        result = parse_care_result({
            'care_mark_candidates': [
                {
                    'kind': 'memory',
                    'status': 'active',
                    'text': f'mark-{index}' + 'x' * 600,
                    'confidence': 4,
                }
                for index in range(8)
            ],
            'read_cue_updates': [
                {
                    'care_mark_public_id': 'care_0001',
                    'term': f'term-{index}' + 'y' * 100,
                    'weight': 2,
                }
                for index in range(12)
            ],
            'touch_care_mark_ids': [
                f'care_{index:04d}' for index in range(20)
            ],
            'include_care_mark_ids': [
                f'care_{index:04d}' for index in range(20)
            ],
        })

        self.assertEqual(len(result.care_mark_candidates), 5)
        self.assertTrue(
            all(len(item.text) <= 500 for item in result.care_mark_candidates)
        )
        self.assertTrue(
            all(item.confidence == 1.0 for item in result.care_mark_candidates)
        )
        self.assertEqual(len(result.read_cue_updates), 8)
        self.assertTrue(
            all(len(item.term) <= 80 for item in result.read_cue_updates)
        )
        self.assertEqual(len(result.touch_care_mark_ids), 8)
        self.assertEqual(len(result.include_care_mark_ids), 8)

    def test_sensitive_active_memory_candidate_becomes_draft(self) -> None:
        result = parse_care_result({
            'care_mark_candidates': [
                {
                    'kind': 'memory',
                    'status': 'active',
                    'text': '通院している',
                },
                {
                    'kind': 'memory',
                    'status': 'active',
                    'text': '友人についての話',
                    'about_other_person': True,
                },
                {
                    'kind': 'memory',
                    'status': 'active',
                    'text': 'センシティブ',
                    'sensitive': True,
                },
            ],
        })
        self.assertEqual(
            [(item.text, item.status) for item in result.care_mark_candidates],
            [
                ('通院している', 'draft'),
                ('友人についての話', 'draft'),
                ('センシティブ', 'draft'),
            ],
        )
