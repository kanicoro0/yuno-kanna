import tempfile
import unittest
from pathlib import Path

from yuno.conversation.repository import ConversationRepository
from yuno.infra.database import Database
from yuno.read_operations import (
    ReadOperation,
    ReadOperationService,
    ReadPersistence,
    ReadPurpose,
    ReadRange,
    ReadSource,
    UnsupportedReadOperation,
)
from yuno.read_operations.service import MAX_LAST_N, MAX_SUMMARY_INPUT_CHARACTERS


class ReadOperationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Database(
            Path(self.temporary_directory.name) / 'read-operations.db'
        )
        await self.database.open()
        self.repository = ConversationRepository(self.database)
        self.service = ReadOperationService(self.repository)
        self.stream = await self.repository.get_or_create_stream(
            'channel', 'channel-1', 'guild-1'
        )

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temporary_directory.cleanup()

    def operation(self, **changes) -> ReadOperation:
        values = {
            'source': ReadSource.CURRENT_STREAM,
            'range': ReadRange.LAST_N,
            'purpose': ReadPurpose.SUMMARIZE,
            'persistence': ReadPersistence.REPLY_ONLY,
            'last_n': 10,
        }
        values.update(changes)
        return ReadOperation(**values)

    async def append(self, number: int, content: str = '') -> None:
        await self.repository.append(
            self.stream.id,
            f'message-{number}',
            'user',
            f'user-{number}',
            f'User {number}',
            content or f'content {number}',
        )

    async def test_last_n_read_is_bounded(self) -> None:
        for number in range(MAX_LAST_N + 8):
            await self.append(number)

        result = await self.service.read(
            self.operation(last_n=MAX_LAST_N + 100),
            current_stream_id=self.stream.id,
        )

        self.assertEqual(result.message_count, MAX_LAST_N)
        self.assertNotIn('content 7\n', result.summary_input)
        self.assertIn(f'content {MAX_LAST_N + 7}', result.summary_input)

    async def test_empty_stream_returns_safe_result(self) -> None:
        result = await self.service.read(
            self.operation(), current_stream_id=self.stream.id
        )

        self.assertTrue(result.is_empty)
        self.assertEqual(result.message_count, 0)
        self.assertIn('Range read:', result.summary_input)
        self.assertNotIn(str(self.stream.id), result.summary_input)

    async def test_summary_input_is_character_bounded(self) -> None:
        for number in range(3):
            await self.append(number, 'x' * MAX_SUMMARY_INPUT_CHARACTERS)

        result = await self.service.read(
            self.operation(last_n=3), current_stream_id=self.stream.id
        )

        self.assertLessEqual(
            len(result.summary_input), MAX_SUMMARY_INPUT_CHARACTERS
        )
        self.assertTrue(result.summary_input.startswith('Range read: last 3'))

    async def test_unsupported_source_and_range_are_rejected(self) -> None:
        unsupported = (
            self.operation(source=ReadSource.CONVERSATION_LOG),
            self.operation(range=ReadRange.YESTERDAY),
        )

        for operation in unsupported:
            with self.subTest(operation=operation):
                with self.assertRaises(UnsupportedReadOperation):
                    await self.service.read(
                        operation, current_stream_id=self.stream.id
                    )

    async def test_result_exposes_no_hidden_internal_fields(self) -> None:
        await self.repository.append(
            self.stream.id,
            'discord-secret-id',
            'user',
            'author-secret-id',
            'Visible name',
            'Visible content',
            reply_to_discord_message_id='hidden-reply-id',
        )

        result = await self.service.read(
            self.operation(last_n=1), current_stream_id=self.stream.id
        )

        self.assertIn('Visible name: Visible content', result.summary_input)
        self.assertEqual(
            set(result.__dict__),
            {'range_read', 'summary_input', 'message_count'},
        )
        for hidden in (
            'discord-secret-id',
            'author-secret-id',
            'hidden-reply-id',
            'context_visible',
            'searchable',
        ):
            self.assertNotIn(hidden, result.summary_input)


if __name__ == '__main__':
    unittest.main()
