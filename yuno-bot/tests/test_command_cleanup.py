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
        self.conversations = conversations
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

    async def test_renderer_keeps_public_ids_for_status_commands_without_scores(self) -> None:
        mark = await self.service.add_mark(
            '10', '1', 'memory', '短い本文', 'active'
        )

        text = render_care_marks((mark,))

        self.assertIn(mark.public_id, text)
        self.assertIn('短い本文', text)
        self.assertNotIn('score', text.casefold())
        self.assertNotIn('weight', text.casefold())
        self.assertNotIn('cue', text.casefold())

    async def test_selected_message_path_keeps_source_identity(self) -> None:
        stream = await self.conversations.get_or_create_stream(
            'channel', '20', '1'
        )
        message = await self.conversations.append(
            stream.id,
            'discord-message-20',
            'user',
            '7',
            'A',
            '選んだ本文',
        )

        result = await self.service.add_mark_from_message(
            '20', 'discord-message-20', 'memory'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.source_message_id, message.id)
        self.assertEqual(result.text, '選んだ本文')
        self.assertEqual((result.kind, result.status), ('memory', 'draft'))

    async def test_selected_message_path_rejects_another_stream(self) -> None:
        stream = await self.conversations.get_or_create_stream(
            'channel', '21', '1'
        )
        await self.conversations.append(
            stream.id,
            'discord-message-21',
            'user',
            '7',
            'A',
            '別の場所',
        )
        await self.conversations.get_or_create_stream('channel', '22', '1')

        result = await self.service.add_mark_from_message(
            '22', 'discord-message-21', 'attention'
        )

        self.assertIsNone(result)


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

    def test_legacy_module_files_are_removed(self) -> None:
        for relative in (
            'yuno/attention/__init__.py',
            'yuno/attention/models.py',
            'yuno/attention/repository.py',
            'yuno/attention/service.py',
            'yuno/interest/__init__.py',
            'yuno/interest/models.py',
            'yuno/interest/repository.py',
            'yuno/interest/service.py',
            'yuno/memory/__init__.py',
            'yuno/memory/models.py',
            'yuno/memory/repository.py',
            'yuno/memory/service.py',
        ):
            self.assertFalse((PROJECT_ROOT / relative).exists(), relative)

    def test_pull_request_ci_runs_split_checks(self) -> None:
        workflow = (
            REPOSITORY_ROOT / '.github' / 'workflows' / 'yuno-check.yml'
        ).read_text(encoding='utf-8')
        self.assertIn('pull_request:', workflow)
        self.assertIn('working-directory: yuno-bot', workflow)
        self.assertIn('python -m compileall main.py yuno tests', workflow)
        self.assertIn('python -m unittest discover -s tests', workflow)
        self.assertIn('from yuno.app import create_bot', workflow)
