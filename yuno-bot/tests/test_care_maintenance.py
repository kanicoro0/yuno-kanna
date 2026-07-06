from pathlib import Path
import tempfile
import unittest

from yuno.care.maintenance import (
    CareMaintenanceAction,
    CareMaintenanceService,
    MAX_AUTOMATIC_CLOSES,
    MAX_MAINTENANCE_ACTIONS,
    MAX_MAINTENANCE_MARKS,
    MAX_MAINTENANCE_MESSAGES,
)
from yuno.care.maintenance_reader import LLMCareMaintenanceReader
from yuno.care.service import CareApplication
from yuno.care_marks.repository import CareMarkRepository
from yuno.care_marks.service import CareMarkService
from yuno.conversation.repository import ConversationRepository
from yuno.infra.database import Database
from yuno.pipeline import ConversationPipeline


class FakeMaintenanceReader:
    def __init__(self, output):
        self.output = output
        self.requests = []

    async def propose(self, request):
        self.requests.append(request)
        return self.output


class CareMaintenanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(
            Path(self.temp_dir.name) / 'maintenance.sqlite3'
        )
        await self.database.open()
        self.conversations = ConversationRepository(self.database)
        self.stream = await self.conversations.get_or_create_stream(
            'channel', '10', '1'
        )
        self.marks = CareMarkService(CareMarkRepository(self.database))
        await self.conversations.append(
            self.stream.id, 'message-1', 'user', '7', 'A', '星の話'
        )

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    async def test_close_merge_and_rewrite_are_proposals_only(self) -> None:
        memory = await self.marks.create(
            self.stream.id, 'memory', 'active', '青色が好き'
        )
        close_target = await self.marks.create(
            self.stream.id, 'attention', 'open', '軽い質問'
        )
        merge_first = await self.marks.create(
            self.stream.id, 'attention', 'open', '星の続き'
        )
        merge_second = await self.marks.create(
            self.stream.id, 'attention', 'open', '星について話す'
        )
        before = {
            mark.public_id: mark
            for mark in await self.marks.list_for_stream(self.stream.id)
        }
        reader = FakeMaintenanceReader({'actions': [
            {
                'action': 'close_attention',
                'target_public_ids': [close_target.public_id],
                'reason': 'もう完了している可能性',
            },
            {
                'action': 'merge_attention',
                'target_public_ids': [
                    merge_first.public_id, merge_second.public_id,
                ],
                'proposed_text': '星の話の続きをする',
            },
            {
                'action': 'rewrite_mark_text',
                'target_public_ids': [memory.public_id],
                'proposed_text': '青色を好む',
            },
        ]})
        service = CareMaintenanceService(
            self.conversations, self.marks, reader
        )

        proposal = await service.propose_for_stream(self.stream.id)

        self.assertEqual(proposal.stream_id, self.stream.id)
        self.assertEqual(
            tuple(action.action for action in proposal.actions),
            ('close_attention', 'merge_attention', 'rewrite_mark_text'),
        )
        self.assertTrue(all(
            isinstance(action, CareMaintenanceAction)
            for action in proposal.actions
        ))
        after = {
            mark.public_id: mark
            for mark in await self.marks.list_for_stream(self.stream.id)
        }
        self.assertEqual(after, before)
        self.assertEqual(after[memory.public_id].text, '青色が好き')
        self.assertEqual(after[close_target.public_id].status, 'open')

    async def test_apply_selected_closes_only_selected_open_attention(self) -> None:
        selected = await self.marks.create(
            self.stream.id, 'attention', 'open', '閉じるもの'
        )
        unrelated = await self.marks.create(
            self.stream.id, 'attention', 'open', '残すもの'
        )
        service = CareMaintenanceService(
            self.conversations,
            self.marks,
            FakeMaintenanceReader({'actions': []}),
        )
        action = CareMaintenanceAction(
            'close_attention', (selected.public_id,)
        )

        result = await service.apply_selected(self.stream.id, action)

        self.assertTrue(result.applied)
        self.assertEqual(
            (await self.marks.get_by_public_id(selected.public_id)).status,
            'closed',
        )
        self.assertEqual(
            (await self.marks.get_by_public_id(unrelated.public_id)).status,
            'open',
        )

    async def test_apply_selected_rejects_stale_or_unsupported_action(self) -> None:
        closed = await self.marks.create(
            self.stream.id, 'attention', 'closed', 'もう閉じている'
        )
        active_memory = await self.marks.create(
            self.stream.id, 'memory', 'active', '書き換えない'
        )
        service = CareMaintenanceService(
            self.conversations,
            self.marks,
            FakeMaintenanceReader({'actions': []}),
        )

        stale = await service.apply_selected(
            self.stream.id,
            CareMaintenanceAction('close_attention', (closed.public_id,)),
        )
        unsupported = await service.apply_selected(
            self.stream.id,
            CareMaintenanceAction(
                'rewrite_mark_text',
                (active_memory.public_id,),
                proposed_text='変えない',
            ),
        )

        self.assertFalse(stale.applied)
        self.assertEqual(stale.reason, 'stale')
        self.assertFalse(unsupported.applied)
        self.assertEqual(unsupported.reason, 'unsupported')
        self.assertEqual(
            (await self.marks.get_by_public_id(closed.public_id)).status,
            'closed',
        )
        unchanged = await self.marks.get_by_public_id(active_memory.public_id)
        self.assertEqual((unchanged.status, unchanged.text), (
            'active', '書き換えない'
        ))

    async def test_auto_maintenance_closes_only_safe_old_attention(self) -> None:
        old = await self.marks.create(
            self.stream.id, 'attention', 'open', '解決した軽い用件'
        )
        unrelated = await self.marks.create(
            self.stream.id, 'attention', 'open', 'まだ続く話'
        )
        newly_created = await self.marks.create(
            self.stream.id, 'attention', 'open', '今できた印'
        )
        reader = FakeMaintenanceReader({'actions': [
            {
                'action': 'close_attention',
                'target_public_ids': [old.public_id],
            },
            {
                'action': 'merge_attention',
                'target_public_ids': [old.public_id, unrelated.public_id],
                'proposed_text': 'まとめる案',
            },
            {
                'action': 'close_attention',
                'target_public_ids': [newly_created.public_id],
            },
        ]})
        service = CareMaintenanceService(
            self.conversations, self.marks, reader
        )

        closed = await service.auto_close_after_activity(
            self.stream.id,
            protected_public_ids=(newly_created.public_id,),
        )

        self.assertEqual(closed, (old.public_id,))
        self.assertEqual(len(reader.requests), 1)
        self.assertEqual(
            (await self.marks.get_by_public_id(old.public_id)).status,
            'closed',
        )
        self.assertEqual(
            (await self.marks.get_by_public_id(unrelated.public_id)).status,
            'open',
        )
        self.assertEqual(
            (await self.marks.get_by_public_id(newly_created.public_id)).status,
            'open',
        )
        for target in (old, unrelated, newly_created):
            self.assertIsNotNone(
                await self.marks.get_by_public_id(target.public_id)
            )

    async def test_auto_maintenance_caps_close_mutations(self) -> None:
        targets = [
            await self.marks.create(
                self.stream.id, 'attention', 'open', f'完了した用件 {index}'
            )
            for index in range(MAX_AUTOMATIC_CLOSES + 1)
        ]
        reader = FakeMaintenanceReader({'actions': [
            {
                'action': 'close_attention',
                'target_public_ids': [target.public_id],
            }
            for target in targets
        ]})
        service = CareMaintenanceService(
            self.conversations, self.marks, reader
        )

        closed = await service.auto_close_after_activity(self.stream.id)

        self.assertEqual(len(closed), MAX_AUTOMATIC_CLOSES)
        statuses = [
            (await self.marks.get_by_public_id(target.public_id)).status
            for target in targets
        ]
        self.assertEqual(statuses.count('closed'), MAX_AUTOMATIC_CLOSES)
        self.assertEqual(statuses.count('open'), 1)

    async def test_pipeline_maintenance_requires_new_care_mark_activity(self) -> None:
        class AutomaticMaintenance:
            def __init__(self):
                self.calls = []

            async def auto_close_after_activity(self, stream_id, **kwargs):
                self.calls.append((stream_id, kwargs))

        maintenance = AutomaticMaintenance()
        pipeline = ConversationPipeline(
            None, None, None, None, maintenance_service=maintenance
        )

        await pipeline._auto_maintain(1, CareApplication())
        await pipeline._auto_maintain(1, CareApplication(
            created_care_mark_ids=('care_0001',),
        ))

        self.assertEqual(len(maintenance.calls), 1)
        self.assertEqual(maintenance.calls[0][0], 1)
        self.assertEqual(
            maintenance.calls[0][1]['protected_public_ids'],
            ('care_0001',),
        )

    async def test_request_context_is_bounded(self) -> None:
        latest = None
        for index in range(25):
            latest = await self.marks.create(
                self.stream.id,
                'attention',
                'open',
                f'確認したいこと {index}',
            )
        for index in range(15):
            await self.conversations.append(
                self.stream.id,
                f'message-{index + 2}',
                'user',
                '7',
                'A',
                ('長い会話 ' + str(index)) * 200,
            )
        reader = FakeMaintenanceReader({'actions': [
            {
                'action': 'keep',
                'target_public_ids': [latest.public_id],
            }
            for _ in range(MAX_MAINTENANCE_ACTIONS + 8)
        ]})
        service = CareMaintenanceService(
            self.conversations, self.marks, reader
        )

        proposal = await service.propose_for_stream(
            self.stream.id, limit=999
        )

        request = reader.requests[0]
        self.assertEqual(len(proposal.actions), MAX_MAINTENANCE_ACTIONS)
        self.assertEqual(len(request.care_marks), MAX_MAINTENANCE_MARKS)
        self.assertEqual(
            len(request.recent_messages), MAX_MAINTENANCE_MESSAGES
        )
        self.assertTrue(all(
            len(message.content) <= 1000
            for message in request.recent_messages
        ))

    async def test_malformed_output_is_ignored_safely(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'attention', 'open', 'まだ見る話'
        )
        malformed_outputs = (
            None,
            {},
            {'actions': 'not-a-list'},
            {'actions': [None, 'bad']},
            {'actions': [{
                'action': 'close_attention',
                'target_public_ids': ['care_missing'],
            }]},
            {'actions': [{
                'action': 'merge_attention',
                'target_public_ids': [mark.public_id],
                'proposed_text': '一件だけ',
            }]},
            {'actions': [{
                'action': 'rewrite_mark_text',
                'target_public_ids': [mark.public_id],
            }]},
        )
        for output in malformed_outputs:
            with self.subTest(output=output):
                service = CareMaintenanceService(
                    self.conversations,
                    self.marks,
                    FakeMaintenanceReader(output),
                )
                proposal = await service.propose_for_stream(self.stream.id)
                self.assertEqual(proposal.actions, ())

        unchanged = await self.marks.get_by_public_id(mark.public_id)
        self.assertEqual((unchanged.status, unchanged.text), ('open', 'まだ見る話'))

    async def test_normal_mark_and_message_work_does_not_run_maintenance(self) -> None:
        class Client:
            def __init__(self):
                self.calls = []

            async def complete_json(self, messages):
                self.calls.append(messages)
                return {'actions': []}

        client = Client()
        reader = LLMCareMaintenanceReader(client)
        CareMaintenanceService(self.conversations, self.marks, reader)

        mark = await self.marks.create(
            self.stream.id, 'memory', 'draft', '残しておく'
        )
        await self.marks.touch(mark.public_id)
        await self.conversations.append(
            self.stream.id, 'message-2', 'user', '7', 'A', '普通の会話'
        )

        self.assertEqual(client.calls, [])


if __name__ == '__main__':
    unittest.main()
