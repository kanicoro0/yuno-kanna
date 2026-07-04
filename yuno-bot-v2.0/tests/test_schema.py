from pathlib import Path
import sqlite3
import tempfile
import unittest

from yuno.infra.database import Database, SCHEMA_VERSION


class SchemaTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_schema_has_care_marks_and_read_cues_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / 'schema.sqlite3')
            await database.open()
            try:
                tables = {
                    row['name']
                    for row in await (await database.connection.execute(
                        'SELECT name FROM sqlite_master WHERE type = \'table\''
                    )).fetchall()
                }
                self.assertTrue({
                    'streams', 'messages', 'listening_channels',
                    'care_marks', 'read_cues',
                }.issubset(tables))
                self.assertTrue({
                    'memory_marks', 'attention_items', 'interest_terms',
                }.isdisjoint(tables))
                columns = {
                    row['name']
                    for row in await (await database.connection.execute(
                        'PRAGMA table_info(care_marks)'
                    )).fetchall()
                }
                self.assertEqual(columns, {
                    'id', 'public_id', 'stream_id', 'source_message_id',
                    'kind', 'status', 'text', 'created_at', 'updated_at',
                    'last_touched_at',
                })
                cue_columns = {
                    row['name']
                    for row in await (await database.connection.execute(
                        'PRAGMA table_info(read_cues)'
                    )).fetchall()
                }
                self.assertEqual(cue_columns, {
                    'id', 'care_mark_id', 'term', 'normalized_term', 'weight',
                    'status', 'created_at', 'updated_at', 'last_touched_at',
                })
            finally:
                await database.close()

    async def test_version_three_schema_is_destructively_reset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reset.sqlite3'
            self._create_version_three_database(path)

            database = Database(path)
            await database.open()
            try:
                tables = {
                    row['name']
                    for row in await (await database.connection.execute(
                        'SELECT name FROM sqlite_master WHERE type = \'table\''
                    )).fetchall()
                }
                self.assertTrue({'care_marks', 'read_cues'}.issubset(tables))
                self.assertTrue({
                    'memory_marks', 'attention_items', 'interest_terms',
                }.isdisjoint(tables))
                row = await (await database.connection.execute(
                    'SELECT MAX(version) AS version FROM schema_migrations'
                )).fetchone()
                self.assertEqual(row['version'], SCHEMA_VERSION)
                message = await (await database.connection.execute(
                    'SELECT content FROM messages WHERE id = 1'
                )).fetchone()
                self.assertEqual(message['content'], 'preserved conversation')
            finally:
                await database.close()

    @staticmethod
    def _create_version_three_database(path: Path) -> None:
        connection = sqlite3.connect(path)
        try:
            connection.executescript(
                '''
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                INSERT INTO schema_migrations VALUES (1, 'now');
                INSERT INTO schema_migrations VALUES (2, 'now');
                INSERT INTO schema_migrations VALUES (3, 'now');

                CREATE TABLE streams (
                    id INTEGER PRIMARY KEY,
                    kind TEXT NOT NULL,
                    discord_channel_id TEXT NOT NULL UNIQUE,
                    discord_guild_id TEXT,
                    created_at TEXT NOT NULL
                );
                INSERT INTO streams VALUES (1, 'channel', '10', '1', 'now');

                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY,
                    stream_id INTEGER NOT NULL,
                    discord_message_id TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL,
                    author_id TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    reply_to_discord_message_id TEXT,
                    created_at TEXT NOT NULL,
                    context_visible INTEGER NOT NULL,
                    searchable INTEGER NOT NULL
                );
                INSERT INTO messages VALUES (
                    1, 1, 'message-1', 'user', '7', 'A',
                    'preserved conversation', NULL, 'now', 1, 1
                );

                CREATE TABLE listening_channels (
                    id INTEGER PRIMARY KEY,
                    discord_channel_id TEXT NOT NULL UNIQUE,
                    discord_guild_id TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE memory_marks (id INTEGER PRIMARY KEY);
                CREATE TABLE attention_items (id INTEGER PRIMARY KEY);
                CREATE TABLE interest_terms (id INTEGER PRIMARY KEY);
                '''
            )
            connection.commit()
        finally:
            connection.close()
