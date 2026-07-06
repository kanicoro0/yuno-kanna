import asyncio
from typing import Iterable, List, Optional

import aiosqlite

from yuno.conversation.models import utc_now
from yuno.infra.database import Database
from yuno.interest.models import InterestTerm


class InterestRepository:
    def __init__(self, database: Database):
        self.database = database
        self._create_lock = asyncio.Lock()

    async def next_public_id(self) -> str:
        row = await (await self.database.connection.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM interest_terms"
        )).fetchone()
        return f"int_{int(row['next_id']):04d}"

    async def upsert_term(
        self, stream_id: int, term: str, weight: float, source: str = "care_reader"
    ) -> InterestTerm:
        if source not in {"care_reader", "memory", "attention", "manual"}:
            raise ValueError("invalid interest source")
        text = term.strip()[:80]
        if not text:
            raise ValueError("interest term must not be empty")
        clamped = max(0.0, min(1.0, float(weight)))
        now = utc_now()
        async with self._create_lock:
            existing = await (await self.database.connection.execute(
                """SELECT * FROM interest_terms
                   WHERE stream_id = ? AND term = ? AND status != 'hidden'""",
                (stream_id, text),
            )).fetchone()
            if existing:
                await self.database.connection.execute(
                    """UPDATE interest_terms
                       SET weight = ?, source = ?, status = 'active',
                           updated_at = ?, last_touched_at = ?
                       WHERE id = ?""",
                    (clamped, source, now, now, existing["id"]),
                )
                public_id = existing["public_id"]
            else:
                public_id = await self.next_public_id()
                await self.database.connection.execute(
                    """INSERT INTO interest_terms(
                        public_id, stream_id, term, weight, status, source,
                        created_at, updated_at, last_touched_at
                    ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
                    (public_id, stream_id, text, clamped, source, now, now, now),
                )
            await self.database.connection.commit()
        item = await self.get_by_public_id(public_id)
        if item is None:
            raise RuntimeError("failed to upsert interest term")
        return item

    async def get_by_public_id(self, public_id: str) -> Optional[InterestTerm]:
        row = await (await self.database.connection.execute(
            "SELECT * FROM interest_terms WHERE public_id = ?", (public_id,)
        )).fetchone()
        return self._model(row) if row else None

    async def list_active_for_stream(self, stream_id: int, limit: int = 8) -> List[InterestTerm]:
        rows = await (await self.database.connection.execute(
            """SELECT * FROM interest_terms
               WHERE stream_id = ? AND status = 'active'
               ORDER BY weight DESC, id DESC LIMIT ?""",
            (stream_id, max(1, min(limit, 100))),
        )).fetchall()
        return [self._model(row) for row in rows]

    async def list_for_stream(
        self, stream_id: int, statuses: Iterable[str], limit: int = 10
    ) -> List[InterestTerm]:
        selected = tuple(value for value in statuses if value in {"active", "sleeping", "hidden"})
        if not selected:
            return []
        placeholders = ",".join("?" for _ in selected)
        rows = await (await self.database.connection.execute(
            f"""SELECT * FROM interest_terms
                WHERE stream_id = ? AND status IN ({placeholders})
                ORDER BY id DESC LIMIT ?""",
            (stream_id, *selected, max(1, min(limit, 20))),
        )).fetchall()
        return [self._model(row) for row in rows]

    async def touch_terms(self, stream_id: int, terms: Iterable[str]) -> None:
        selected = list(dict.fromkeys(term.strip() for term in terms if term.strip()))[:8]
        if not selected:
            return
        now = utc_now()
        placeholders = ",".join("?" for _ in selected)
        await self.database.connection.execute(
            f"""UPDATE interest_terms SET last_touched_at = ?, updated_at = ?
                WHERE stream_id = ? AND status = 'active'
                  AND term IN ({placeholders})""",
            (now, now, stream_id, *selected),
        )
        await self.database.connection.commit()

    async def hide(self, public_id: str) -> Optional[InterestTerm]:
        return await self.set_status(public_id, "hidden")

    async def sleep(self, public_id: str) -> Optional[InterestTerm]:
        return await self.set_status(public_id, "sleeping")

    async def wake(self, public_id: str) -> Optional[InterestTerm]:
        return await self.set_status(public_id, "active")

    async def set_status(self, public_id: str, status: str) -> Optional[InterestTerm]:
        if status not in {"active", "sleeping", "hidden"}:
            raise ValueError("invalid interest status")
        await self.database.connection.execute(
            "UPDATE interest_terms SET status = ?, updated_at = ? WHERE public_id = ?",
            (status, utc_now(), public_id),
        )
        await self.database.connection.commit()
        return await self.get_by_public_id(public_id)

    @staticmethod
    def _model(row: aiosqlite.Row) -> InterestTerm:
        return InterestTerm(**dict(row))
