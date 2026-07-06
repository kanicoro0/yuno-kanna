import json
import unittest

from yuno.care.maintenance import (
    CareMaintenanceMark,
    CareMaintenanceMessage,
    CareMaintenanceRequest,
    MAX_MAINTENANCE_MARKS,
    MAX_MAINTENANCE_MESSAGES,
    parse_maintenance_proposal,
)
from yuno.care.maintenance_reader import (
    CARE_MAINTENANCE_SYSTEM_PROMPT,
    LLMCareMaintenanceReader,
)
from yuno.care_marks.models import CareMark


class FakeJSONClient:
    def __init__(self, output):
        self.output = output
        self.calls = []

    async def complete_json(self, messages):
        self.calls.append(messages)
        return self.output


def mark(public_id, *, kind='attention', status='open', text='星の話'):
    return CareMark(
        id=int(public_id.split('_')[-1]),
        public_id=public_id,
        stream_id=1,
        source_message_id=None,
        kind=kind,
        status=status,
        text=text,
        created_at='now',
        updated_at='now',
    )


def request(mark_count=1, message_count=1):
    return CareMaintenanceRequest(
        stream_id=1,
        care_marks=tuple(
            CareMaintenanceMark(
                f'care_{index + 1:04d}',
                'attention',
                'open',
                '長い印' * 200,
                False,
            )
            for index in range(mark_count)
        ),
        recent_messages=tuple(
            CareMaintenanceMessage('user', '長い会話' * 400)
            for _ in range(message_count)
        ),
    )


class LLMCareMaintenanceReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_reader_makes_one_bounded_structured_call(self) -> None:
        output = {'actions': []}
        client = FakeJSONClient(output)
        reader = LLMCareMaintenanceReader(client)

        raw = await reader.propose(request(25, 18))

        self.assertIs(raw, output)
        self.assertEqual(len(client.calls), 1)
        messages = client.calls[0]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]['role'], 'system')
        self.assertEqual(messages[0]['content'], CARE_MAINTENANCE_SYSTEM_PROMPT)
        payload = json.loads(messages[1]['content'])
        self.assertEqual(len(payload['care_marks']), MAX_MAINTENANCE_MARKS)
        self.assertEqual(
            len(payload['recent_messages']), MAX_MAINTENANCE_MESSAGES
        )
        self.assertTrue(all(
            len(item['text']) <= 500 for item in payload['care_marks']
        ))
        self.assertTrue(all(
            len(item['content']) <= 1000
            for item in payload['recent_messages']
        ))

    async def test_structured_output_is_accepted_by_existing_parser(self) -> None:
        first = mark('care_0001')
        second = mark('care_0002')
        output = {'actions': [{
            'action': 'merge_attention',
            'target_public_ids': [first.public_id, second.public_id],
            'proposed_text': '星の話を続ける',
            'reason': '同じ話題',
        }]}
        client = FakeJSONClient(output)

        raw = await LLMCareMaintenanceReader(client).propose(request(2, 1))
        proposal = parse_maintenance_proposal(1, raw, (first, second))

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(proposal.actions), 1)
        self.assertEqual(proposal.actions[0].action, 'merge_attention')
        self.assertEqual(
            proposal.actions[0].target_public_ids,
            ('care_0001', 'care_0002'),
        )

    async def test_malformed_output_becomes_safe_empty_proposal(self) -> None:
        existing = mark('care_0001')
        for output in (None, [], 'bad-json-shape'):
            with self.subTest(output=output):
                client = FakeJSONClient(output)
                raw = await LLMCareMaintenanceReader(client).propose(request())
                proposal = parse_maintenance_proposal(1, raw, (existing,))

                self.assertEqual(len(client.calls), 1)
                self.assertEqual(raw, {})
                self.assertEqual(proposal.actions, ())


if __name__ == '__main__':
    unittest.main()
