from pathlib import Path
import tempfile
import unittest

from yuno.care_marks.repository import CareMarkRepository
from yuno.care_marks.service import CareMarkService
from yuno.commands.admin_service import CareMarkCommandService
from yuno.commands.core import render_care_marks
from yuno.conversation.repository import ConversationRepository
from yuno.infra.database import Database


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent


class CareMarkCommandServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / 'commands.sqlite3')
        await self.database.open()
        conversations = ConversationRepository(self.database)
        marks = CareMarkService(CareMarkRepository(self.database))
        self.service = CareMarkCommandService(conversations, marks)

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    async def test_care_mark_command_service_uses_schema_v4_path(self) -> None:
        memory = await self.service.add_mark(
            '10', '1', 'memory', '残す印'
        )
        attention = await self.service.add_mark(
            '10', '1', 'attention', '開いた話'
        )
        sensitive = await self.service.add_mark(
            '10', '1', 'memory', '通院について', 'active'
        )

        self.assertEqual(memory.status, 'draft')
        self.assertEqual(attention.status, 'open')
        self.assertEqual(sensitive.status, 'draft')
        visible = await self.service.list_marks(
            '10', '1', status='visible'
        )
        self.assertEqual(
            [mark.public_id for mark in visible],
            [attention.public_id],
        )
        activated = await self.service.set_status(
            '10', memory.public_id, 'active'
        )
        self.assertEqual(activated.status, 'active')

    async def test_renderer_has_no_internal_scores_or_cues(self) -> None:
        mark = await self.service.add_mark(
            '10', '1', 'memory', '短い本文', 'active'
        )

        text = render_care_marks((mark,))

        self.assertNotIn(mark.public_id, text)
        self.assertIn('短い本文', text)
        self.assertNotIn('score', text.casefold())
        self.assertNotIn('weight', text.casefold())
        self.assertNotIn('cue', text.casefold())


class CommandCleanupGuardTests(unittest.TestCase):
    def test_normal_app_and_command_wiring_has_no_legacy_services(self) -> None:
        source = '\n'.join(
            (PROJECT_ROOT / relative).read_text(encoding='utf-8')
            for relative in (
                'yuno/app.py',
                'yuno/commands/admin_service.py',
                'yuno/commands/core.py',
            )
        )
        for forbidden in (
            'MemoryMarkRepository',
            'AttentionRepository',
            'InterestRepository',
            'CoreAdminService',
            'create_memory_group',
            'create_attention_group',
            'create_interest_group',
        ):
            self.assertNotIn(forbidden, source)

    def test_pull_request_ci_runs_standard_check(self) -> None:
        workflow = (
            REPOSITORY_ROOT / '.github' / 'workflows' / 'yuno-check.yml'
        ).read_text(encoding='utf-8')
        self.assertIn('pull_request:', workflow)
        self.assertIn('python scripts/check_yuno.py', workflow)
