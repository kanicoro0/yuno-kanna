import asyncio
from typing import Iterable, List, Optional

import aiosqlite

from yuno.attention.models import AttentionItem
from yuno.conversation.models import utc_now
from yuno.infra.database import Database


class AttentionRepository:
    def __init__(self, database: Database):
        self.database = database
        self._create_lock = asyncio.Lock()

    async def next_public_id(self) -> str:
        row = await (await self.database.connection.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM attention_items"
        )).fetchone()
        return f"att_{int(row['next_id']):04d}"

    async def create(
        self, stream_id: int, text: str, source_message_id: Optional[int] = None,
        memory_mark_id: Optional[int] = None, rank: float = 0.5,
    ) -> AttentionItem:
        content = text.strip()[:400]
        if not content:
            raise ValueError("attention text must not be empty")
        now = utc_now()
        async with self._create_lock:
            public_id = await self.next_public_id()
            cursor = await self.database.connection.execute(
                """INSERT INTO attention_items(
                    public_id, stream_id, source_message_id, memory_mark_id,
                    status, text, rank, created_at, updated_at, last_touched_at
                ) VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)""",
                (
                    public_id, stream_id, source_message_id, memory_mark_id,
                    content, max(0.0, min(1.0, float(rank))), now, now, now,
                ),
            )
            await self.database.connection.commit()
            row = await (await self.database.connection.execute(
                "SELECT * FROM attention_items WHERE id = ?", (cursor.lastrowid,)
            )).fetchone()
        return self._model(row)

    async def get_by_public_id(self, public_id: str) -> Optional[AttentionItem]:
        row = await (await self.database.connection.execute(
            "SELECT * FROM attention_items WHERE public_id = ?", (public_id,)
        )).fetchone()
        return self._model(row) if row else None

    async def list_open_for_stream(self, stream_id: int, limit: int = 8) -> List[AttentionItem]:
        rows = await (await self.database.connection.execute(
            """SELECT * FROM attention_items
               WHERE stream_id = ? AND status = 'open'
               ORDER BY rank DESC, id DESC LIMIT ?""",
            (stream_id, max(1, min(limit, 100))),
        )).fetchall()
        return [self._model(row) for row in rows]

    async def list_for_stream(
        self, stream_id: int, statuses: Iterable[str], limit: int = 10
    ) -> List[AttentionItem]:
        selected = tuple(value for value in statuses if value in {"open", "closed", "hidden"})
        if not selected:
            return []
        placeholders = ",".join("?" for _ in selected)
        rows = await (await self.database.connection.execute(
            f"""SELECT * FROM attention_items
                WHERE stream_id = ? AND status IN ({placeholders})
                ORDER BY id DESC LIMIT ?""",
            (stream_id, *selected, max(1, min(limit, 20))),
        )).fetchall()
        return [self._model(row) for row in rows]

    async def touch(self, public_id: str) -> Optional[AttentionItem]:
        now = utc_now()
        await self.database.connection.execute(
            """UPDATE attention_items
               SET updated_at = ?, last_touched_at = ?
               WHERE public_id = ? AND status = 'open'""",
            (now, now, public_id),
        )
        await self.database.connection.commit()
        return await self.get_by_public_id(public_id)

    async def close(self, public_id: str) -> Optional[AttentionItem]:
        return await self._set_status(public_id, "closed")

    async def hide(self, public_id: str) -> Optional[AttentionItem]:
        return await self._set_status(public_id, "hidden")

    async def reopen(self, public_id: str) -> Optional[AttentionItem]:
        return await self._set_status(public_id, "open")

    async def _set_status(self, public_id: str, status: str) -> Optional[AttentionItem]:
        now = utc_now()
        await self.database.connection.execute(
            """UPDATE attention_items
               SET status = ?, updated_at = ?, closed_at = ?, hidden_at = ?
               WHERE public_id = ?""",
            (
                status, now, now if status == "closed" else None,
                now if status == "hidden" else None, public_id,
            ),
        )
        await self.database.connection.commit()
        return await self.get_by_public_id(public_id)

    @staticmethod
    def _model(row: aiosqlite.Row) -> AttentionItem:
        return AttentionItem(**dict(row))
