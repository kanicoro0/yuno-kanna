from pathlib import Path
import sqlite3
import tempfile
import unittest

from yuno.conversation.repository import ConversationRepository
from yuno.infra.database import Database


class SchemaV2MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_v1_database_migrates_without_losing_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "migration.sqlite3"
            initial = Database(path)
            await initial.open()
            repository = ConversationRepository(initial)
            stream = await repository.get_or_create_stream("channel", "10", "1")
            await repository.append(stream.id, "m1", "user", "7", "A", "残る会話")
            await initial.close()

            connection = sqlite3.connect(path)
            try:
                connection.executescript(
                    """
                    DROP TABLE interest_terms;
                    DROP TABLE attention_items;
                    DROP TABLE memory_marks;
                    DROP TABLE listening_channels;
                    DELETE FROM schema_migrations WHERE version >= 2;
                    """
                )
                connection.commit()
            finally:
                connection.close()

            migrated = Database(path)
            await migrated.open()
            try:
                tables = {
                    row["name"] for row in await (await migrated.connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )).fetchall()
                }
                self.assertTrue({
                    "streams", "messages", "memory_marks",
                    "attention_items", "interest_terms", "listening_channels",
                }.issubset(tables))
                versions = [
                    row["version"] for row in await (await migrated.connection.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    )).fetchall()
                ]
                self.assertEqual(versions, [1, 2, 3])
                row = await (await migrated.connection.execute(
                    "SELECT content FROM messages WHERE discord_message_id = 'm1'"
                )).fetchone()
                self.assertEqual(row["content"], "残る会話")
            finally:
                await migrated.close()

    async def test_v2_database_adds_listening_table_without_losing_core_tables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v2-to-v3.sqlite3"
            initial = Database(path)
            await initial.open()
            await initial.close()
            connection = sqlite3.connect(path)
            try:
                connection.executescript(
                    """
                    DROP TABLE listening_channels;
                    DELETE FROM schema_migrations WHERE version = 3;
                    """
                )
                connection.commit()
            finally:
                connection.close()

            migrated = Database(path)
            await migrated.open()
            try:
                tables = {
                    row["name"] for row in await (await migrated.connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )).fetchall()
                }
                self.assertIn("listening_channels", tables)
                self.assertTrue({"memory_marks", "attention_items", "interest_terms"}.issubset(tables))
                row = await (await migrated.connection.execute(
                    "SELECT MAX(version) AS version FROM schema_migrations"
                )).fetchone()
                self.assertEqual(row["version"], 3)
            finally:
                await migrated.close()
