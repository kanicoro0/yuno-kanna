import asyncio
from pathlib import Path
import tempfile
import unittest

from yuno.conversation.context import build_speaker_history
from yuno.conversation.models import ConversationMessage
from yuno.conversation.repository import ConversationRepository
from yuno.infra.database import Database


class ConversationRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "yuno.sqlite3"
        self.database = Database(self.path)
        await self.database.open()
        self.repository = ConversationRepository(self.database)

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    async def test_messages_survive_restart(self) -> None:
        stream = await self.repository.get_or_create_stream("channel", "10", "1")
        await self.repository.append(stream.id, "100", "user", "7", "きみ", "続きの話")
        await self.database.close()

        self.database = Database(self.path)
        await self.database.open()
        self.repository = ConversationRepository(self.database)
        reopened = await self.repository.get_or_create_stream("channel", "10", "1")
        recent = await self.repository.recent(reopened.id)

        self.assertEqual([item.content for item in recent], ["続きの話"])

    async def test_streams_do_not_leak_into_each_other(self) -> None:
        first = await self.repository.get_or_create_stream("channel", "10", "1")
        second = await self.repository.get_or_create_stream("channel", "20", "1")
        dm = await self.repository.get_or_create_stream("dm", "30", None)
        await self.repository.append(first.id, "101", "user", "7", "A", "first")
        await self.repository.append(second.id, "102", "user", "7", "A", "second")
        await self.repository.append(dm.id, "103", "user", "7", "A", "private")

        self.assertEqual([m.content for m in await self.repository.recent(first.id)], ["first"])
        self.assertEqual([m.content for m in await self.repository.recent(second.id)], ["second"])
        self.assertEqual([m.content for m in await self.repository.recent(dm.id)], ["private"])

    async def test_duplicate_discord_message_is_idempotent(self) -> None:
        stream = await self.repository.get_or_create_stream("channel", "10", "1")
        first = await self.repository.append(stream.id, "100", "user", "7", "A", "same")
        second = await self.repository.append(stream.id, "100", "user", "7", "A", "same")

        self.assertEqual(first.id, second.id)
        self.assertEqual(await self.repository.count_messages(stream.id), 1)

    async def test_concurrent_appends_are_retained(self) -> None:
        stream = await self.repository.get_or_create_stream("channel", "10", "1")
        await asyncio.gather(*[
            self.repository.append(stream.id, str(index), "user", "7", "A", f"m{index}")
            for index in range(1, 11)
        ])
        self.assertEqual(await self.repository.count_messages(stream.id), 10)


class ContextTests(unittest.TestCase):
    def test_context_keeps_newest_messages_under_character_limit(self) -> None:
        messages = [
            ConversationMessage(
                id=index,
                stream_id=1,
                discord_message_id=str(index),
                role="user",
                author_id="7",
                author_name="A",
                content=value,
                reply_to_discord_message_id=None,
                created_at="now",
            )
            for index, value in enumerate(["old", "middle", "new"], start=1)
        ]
        history = build_speaker_history(messages, character_limit=14)
        self.assertEqual(history, [{"role": "user", "content": "A: new"}])

    def test_author_name_is_kept_for_human_messages(self) -> None:
        message = ConversationMessage(
            id=1,
            stream_id=1,
            discord_message_id="1",
            role="user",
            author_id="7",
            author_name="こはる",
            content="おはよう",
            reply_to_discord_message_id=None,
            created_at="now",
        )
        self.assertEqual(
            build_speaker_history([message]),
            [{"role": "user", "content": "こはる: おはよう"}],
        )
