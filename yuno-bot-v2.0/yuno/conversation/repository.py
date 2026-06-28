from typing import List, Optional

import aiosqlite

from yuno.conversation.models import ConversationMessage, Stream, utc_now
from yuno.infra.database import Database


class ConversationRepository:
    def __init__(self, database: Database):
        self.database = database

    async def get_or_create_stream(
        self,
        kind: str,
        discord_channel_id: str,
        discord_guild_id: Optional[str],
    ) -> Stream:
        if kind not in {"channel", "dm"}:
            raise ValueError("invalid stream kind")
        connection = self.database.connection
        await connection.execute(
            """
            INSERT INTO streams(kind, discord_channel_id, discord_guild_id, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(discord_channel_id) DO NOTHING
            """,
            (kind, discord_channel_id, discord_guild_id, utc_now()),
        )
        await connection.commit()
        row = await (await connection.execute(
            "SELECT * FROM streams WHERE discord_channel_id = ?",
            (discord_channel_id,),
        )).fetchone()
        if row is None:
            raise RuntimeError("failed to create conversation stream")
        if row["kind"] != kind or row["discord_guild_id"] != discord_guild_id:
            raise ValueError("Discord channel is already bound to a different stream")
        return self._stream(row)

    async def append(
        self,
        stream_id: int,
        discord_message_id: str,
        role: str,
        author_id: str,
        author_name: str,
        content: str,
        reply_to_discord_message_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> ConversationMessage:
        if role not in {"user", "assistant"}:
            raise ValueError("invalid conversation role")
        if not content.strip():
            raise ValueError("message content must not be empty")
        connection = self.database.connection
        try:
            await connection.execute(
                """
                INSERT INTO messages(
                    stream_id, discord_message_id, role, author_id, author_name,
                    content, reply_to_discord_message_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stream_id,
                    discord_message_id,
                    role,
                    author_id,
                    author_name[:100],
                    content,
                    reply_to_discord_message_id,
                    created_at or utc_now(),
                ),
            )
            await connection.commit()
        except aiosqlite.IntegrityError:
            await connection.rollback()
        row = await (await connection.execute(
            "SELECT * FROM messages WHERE discord_message_id = ?",
            (discord_message_id,),
        )).fetchone()
        if row is None:
            raise RuntimeError("failed to append conversation message")
        if row["stream_id"] != stream_id:
            raise ValueError("Discord message is already bound to another stream")
        return self._message(row)

    async def recent(self, stream_id: int, limit: int = 12) -> List[ConversationMessage]:
        safe_limit = max(1, min(limit, 100))
        rows = await (await self.database.connection.execute(
            """
            SELECT * FROM messages
            WHERE stream_id = ? AND context_visible = 1
            ORDER BY id DESC
            LIMIT ?
            """,
            (stream_id, safe_limit),
        )).fetchall()
        return [self._message(row) for row in reversed(rows)]

    async def count_messages(self, stream_id: int) -> int:
        row = await (await self.database.connection.execute(
            "SELECT COUNT(*) AS count FROM messages WHERE stream_id = ?",
            (stream_id,),
        )).fetchone()
        return int(row["count"])

    @staticmethod
    def _stream(row: aiosqlite.Row) -> Stream:
        return Stream(
            id=row["id"],
            kind=row["kind"],
            discord_channel_id=row["discord_channel_id"],
            discord_guild_id=row["discord_guild_id"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _message(row: aiosqlite.Row) -> ConversationMessage:
        return ConversationMessage(
            id=row["id"],
            stream_id=row["stream_id"],
            discord_message_id=row["discord_message_id"],
            role=row["role"],
            author_id=row["author_id"],
            author_name=row["author_name"],
            content=row["content"],
            reply_to_discord_message_id=row["reply_to_discord_message_id"],
            created_at=row["created_at"],
            context_visible=bool(row["context_visible"]),
            searchable=bool(row["searchable"]),
        )
