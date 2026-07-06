import asyncio
from typing import Iterable, List, Optional

import aiosqlite

from yuno.care_marks.models import CareMark
from yuno.conversation.models import utc_now
from yuno.infra.database import Database


class CareMarkRepository:
    def __init__(self, database: Database):
        self.database = database
        self._create_lock = asyncio.Lock()

    async def create(
        self,
        stream_id: int,
        source_message_id: Optional[int],
        kind: str,
        status: str,
        text: str,
    ) -> CareMark:
        now = utc_now()
        async with self._create_lock:
            row = await (await self.database.connection.execute(
                'SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM care_marks'
            )).fetchone()
            next_id = int(row['next_id'])
            public_id = f'care_{next_id:04d}'
            cursor = await self.database.connection.execute(
                '''INSERT INTO care_marks(
                       public_id, stream_id, source_message_id, kind, status, text,
                       created_at, updated_at, last_touched_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)''',
                (public_id, stream_id, source_message_id, kind, status, text, now, now),
            )
            await self.database.connection.commit()
        mark = await self.get(int(cursor.lastrowid))
        if mark is None:
            raise RuntimeError('care mark insert did not return a row')
        return mark

    async def get(self, care_mark_id: int) -> Optional[CareMark]:
        row = await (await self.database.connection.execute(
            'SELECT * FROM care_marks WHERE id = ?', (care_mark_id,)
        )).fetchone()
        return self._model(row) if row else None

    async def get_by_public_id(self, public_id: str) -> Optional[CareMark]:
        row = await (await self.database.connection.execute(
            'SELECT * FROM care_marks WHERE public_id = ?', (public_id,)
        )).fetchone()
        return self._model(row) if row else None

    async def list_for_stream(
        self,
        stream_id: int,
        kinds: Iterable[str] = ('memory', 'attention'),
        statuses: Optional[Iterable[str]] = None,
        limit: int = 20,
    ) -> List[CareMark]:
        selected_kinds = tuple(dict.fromkeys(kinds))
        if not selected_kinds:
            return []
        clauses = ['stream_id = ?']
        parameters = [stream_id]
        placeholders = ','.join('?' for _ in selected_kinds)
        clauses.append(f'kind IN ({placeholders})')
        parameters.extend(selected_kinds)
        if statuses is not None:
            selected_statuses = tuple(dict.fromkeys(statuses))
            if not selected_statuses:
                return []
            placeholders = ','.join('?' for _ in selected_statuses)
            clauses.append(f'status IN ({placeholders})')
            parameters.extend(selected_statuses)
        parameters.append(max(1, min(int(limit), 100)))
        where_clause = ' AND '.join(clauses)
        rows = await (await self.database.connection.execute(
            f'''SELECT * FROM care_marks
                WHERE {where_clause}
                ORDER BY id DESC LIMIT ?''',
            tuple(parameters),
        )).fetchall()
        return [self._model(row) for row in rows]

    async def list_for_source(
        self,
        stream_id: int,
        source_message_id: int,
        kind: str,
    ) -> List[CareMark]:
        rows = await (await self.database.connection.execute(
            '''SELECT * FROM care_marks
               WHERE stream_id = ? AND source_message_id = ? AND kind = ?
               ORDER BY id DESC''',
            (stream_id, source_message_id, kind),
        )).fetchall()
        return [self._model(row) for row in rows]

    async def update(
        self, care_mark_id: int, *, status: str, text: str
    ) -> Optional[CareMark]:
        await self.database.connection.execute(
            '''UPDATE care_marks
               SET status = ?, text = ?, updated_at = ? WHERE id = ?''',
            (status, text, utc_now(), care_mark_id),
        )
        await self.database.connection.commit()
        return await self.get(care_mark_id)

    async def touch(self, care_mark_id: int) -> Optional[CareMark]:
        now = utc_now()
        await self.database.connection.execute(
            '''UPDATE care_marks SET last_touched_at = ?, updated_at = ?
               WHERE id = ?''',
            (now, now, care_mark_id),
        )
        await self.database.connection.commit()
        return await self.get(care_mark_id)

    async def delete(self, care_mark_id: int) -> bool:
        cursor = await self.database.connection.execute(
            'DELETE FROM care_marks WHERE id = ?', (care_mark_id,)
        )
        await self.database.connection.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _model(row: aiosqlite.Row) -> CareMark:
        return CareMark(**dict(row))
