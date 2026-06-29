from pathlib import Path
from typing import Optional

import aiosqlite


SCHEMA_VERSION = 3


class Database:
    """One SQLite connection for the single-process bot runtime."""

    def __init__(self, path: Path):
        self.path = path
        self._connection: Optional[aiosqlite.Connection] = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("database is not open")
        return self._connection

    async def open(self) -> None:
        if self._connection is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.execute("PRAGMA busy_timeout = 5000")
        if str(self.path) != ":memory:":
            await self._connection.execute("PRAGMA journal_mode = WAL")
        await self._migrate()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def _migrate(self) -> None:
        connection = self.connection
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        row = await (await connection.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
        )).fetchone()
        current = int(row["version"])
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"database schema {current} is newer than supported schema {SCHEMA_VERSION}"
            )
        if current < 1:
            await connection.executescript(
                """
                CREATE TABLE streams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK (kind IN ('channel', 'dm')),
                    discord_channel_id TEXT NOT NULL UNIQUE,
                    discord_guild_id TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stream_id INTEGER NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
                    discord_message_id TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    author_id TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    reply_to_discord_message_id TEXT,
                    created_at TEXT NOT NULL,
                    context_visible INTEGER NOT NULL DEFAULT 1 CHECK (context_visible IN (0, 1)),
                    searchable INTEGER NOT NULL DEFAULT 1 CHECK (searchable IN (0, 1))
                );

                CREATE INDEX messages_stream_recent
                    ON messages(stream_id, id DESC);
                CREATE INDEX messages_stream_visible
                    ON messages(stream_id, context_visible, id DESC);
                """
            )
            await connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (1, datetime('now'))"
            )
        if current < 2:
            await connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_marks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    public_id TEXT NOT NULL UNIQUE,
                    stream_id INTEGER REFERENCES streams(id) ON DELETE CASCADE,
                    source_message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL CHECK (kind IN ('pin', 'correction')),
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'active', 'hidden')),
                    content TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.5,
                    provenance TEXT NOT NULL DEFAULT 'care_reader'
                        CHECK (provenance IN ('care_reader', 'manual', 'legacy')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    hidden_at TEXT,
                    legacy_source_id TEXT,
                    legacy_import_batch_id TEXT
                );

                CREATE INDEX IF NOT EXISTS memory_marks_stream_status
                    ON memory_marks(stream_id, status, id DESC);
                CREATE INDEX IF NOT EXISTS memory_marks_source_message
                    ON memory_marks(source_message_id);
                CREATE UNIQUE INDEX IF NOT EXISTS memory_marks_legacy_unique
                    ON memory_marks(legacy_source_id)
                    WHERE legacy_source_id IS NOT NULL;

                CREATE TABLE IF NOT EXISTS attention_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    public_id TEXT NOT NULL UNIQUE,
                    stream_id INTEGER NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
                    source_message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
                    memory_mark_id INTEGER REFERENCES memory_marks(id) ON DELETE SET NULL,
                    status TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'closed', 'hidden')),
                    text TEXT NOT NULL,
                    rank REAL NOT NULL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_touched_at TEXT,
                    closed_at TEXT,
                    hidden_at TEXT
                );

                CREATE INDEX IF NOT EXISTS attention_items_stream_status
                    ON attention_items(stream_id, status, rank DESC, id DESC);

                CREATE TABLE IF NOT EXISTS interest_terms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    public_id TEXT NOT NULL UNIQUE,
                    stream_id INTEGER NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
                    term TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 0.3,
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'sleeping', 'hidden')),
                    source TEXT NOT NULL DEFAULT 'care_reader'
                        CHECK (source IN ('care_reader', 'memory', 'attention', 'manual')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_touched_at TEXT
                );

                CREATE INDEX IF NOT EXISTS interest_terms_stream_status
                    ON interest_terms(stream_id, status, weight DESC, id DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS interest_terms_unique_active
                    ON interest_terms(stream_id, term)
                    WHERE status != 'hidden';
                """
            )
            await connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (2, datetime('now'))"
            )
        if current < 3:
            await connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS listening_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_channel_id TEXT NOT NULL UNIQUE,
                    discord_guild_id TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS listening_channels_guild
                    ON listening_channels(discord_guild_id, discord_channel_id);
                """
            )
            await connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (3, datetime('now'))"
            )
        await connection.commit()
