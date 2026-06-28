from pathlib import Path
from typing import Optional

import aiosqlite


SCHEMA_VERSION = 1


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
        await connection.commit()
