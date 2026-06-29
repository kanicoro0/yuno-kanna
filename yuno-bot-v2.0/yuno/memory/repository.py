import asyncio
from typing import Iterable, List, Optional

import aiosqlite

from yuno.conversation.models import utc_now
from yuno.infra.database import Database
from yuno.memory.models import MemoryMark


class MemoryMarkRepository:
    def __init__(self, database: Database):
        self.database = database
        self._create_lock = asyncio.Lock()

    async def next_public_id(self) -> str:
        row = await (await self.database.connection.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM memory_marks"
        )).fetchone()
        return f"mem_{int(row['next_id']):04d}"

    async def create(
        self,
        stream_id: Optional[int],
        source_message_id: Optional[int],
        kind: str,
        status: str,
        content: str,
        confidence: float = 0.5,
        provenance: str = "care_reader",
        legacy_source_id: Optional[str] = None,
        legacy_import_batch_id: Optional[str] = None,
    ) -> MemoryMark:
        if kind not in {"pin", "correction"}:
            raise ValueError("invalid memory mark kind")
        if status not in {"pending", "active", "hidden"}:
            raise ValueError("invalid memory mark status")
        if provenance not in {"care_reader", "manual", "legacy"}:
            raise ValueError("invalid memory mark provenance")
        text = content.strip()[:500]
        if not text:
            raise ValueError("memory mark content must not be empty")
        now = utc_now()
        async with self._create_lock:
            public_id = await self.next_public_id()
            cursor = await self.database.connection.execute(
                """
                INSERT INTO memory_marks(
                    public_id, stream_id, source_message_id, kind, status, content,
                    confidence, provenance, created_at, updated_at, hidden_at,
                    legacy_source_id, legacy_import_batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    public_id, stream_id, source_message_id, kind, status, text,
                    max(0.0, min(1.0, float(confidence))), provenance, now, now,
                    now if status == "hidden" else None,
                    legacy_source_id, legacy_import_batch_id,
                ),
            )
            await self.database.connection.commit()
            row = await (await self.database.connection.execute(
                "SELECT * FROM memory_marks WHERE id = ?", (cursor.lastrowid,)
            )).fetchone()
        return self._model(row)

    async def get_by_public_id(self, public_id: str) -> Optional[MemoryMark]:
        row = await (await self.database.connection.execute(
            "SELECT * FROM memory_marks WHERE public_id = ?", (public_id,)
        )).fetchone()
        return self._model(row) if row else None

    async def list_for_stream(
        self, stream_id: int, statuses: Iterable[str], limit: int = 8
    ) -> List[MemoryMark]:
        selected = tuple(status for status in statuses if status in {"pending", "active", "hidden"})
        if not selected:
            return []
        placeholders = ",".join("?" for _ in selected)
        rows = await (await self.database.connection.execute(
            f"""SELECT * FROM memory_marks
                WHERE stream_id = ? AND status IN ({placeholders})
                ORDER BY id DESC LIMIT ?""",
            (stream_id, *selected, max(1, min(limit, 100))),
        )).fetchall()
        return [self._model(row) for row in rows]

    async def search_for_stream(
        self, stream_id: int, query: str, statuses: Iterable[str], limit: int = 8
    ) -> List[MemoryMark]:
        selected = tuple(status for status in statuses if status in {"pending", "active", "hidden"})
        if not selected or not query.strip():
            return []
        placeholders = ",".join("?" for _ in selected)
        escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = await (await self.database.connection.execute(
            f"""SELECT * FROM memory_marks
                WHERE stream_id = ? AND status IN ({placeholders})
                  AND content LIKE ? ESCAPE '\\'
                ORDER BY id DESC LIMIT ?""",
            (stream_id, *selected, f"%{escaped}%", max(1, min(limit, 100))),
        )).fetchall()
        return [self._model(row) for row in rows]

    async def activate(self, public_id: str) -> Optional[MemoryMark]:
        return await self._set_status(public_id, "active")

    async def hide(self, public_id: str) -> Optional[MemoryMark]:
        return await self._set_status(public_id, "hidden")

    async def restore_to_pending(self, public_id: str) -> Optional[MemoryMark]:
        return await self._set_status(public_id, "pending")

    async def _set_status(self, public_id: str, status: str) -> Optional[MemoryMark]:
        now = utc_now()
        await self.database.connection.execute(
            """UPDATE memory_marks SET status = ?, updated_at = ?, hidden_at = ?
               WHERE public_id = ?""",
            (status, now, now if status == "hidden" else None, public_id),
        )
        await self.database.connection.commit()
        return await self.get_by_public_id(public_id)

    @staticmethod
    def _model(row: aiosqlite.Row) -> MemoryMark:
        return MemoryMark(**dict(row))
