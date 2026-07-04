from typing import Iterable, List, Optional

import aiosqlite

from yuno.conversation.models import utc_now
from yuno.infra.database import Database
from yuno.read_cues.models import ReadCue


class ReadCueRepository:
    def __init__(self, database: Database):
        self.database = database

    async def upsert(
        self,
        care_mark_id: int,
        term: str,
        normalized_term: str,
        weight: float,
        status: str,
    ) -> ReadCue:
        now = utc_now()
        await self.database.connection.execute(
            '''INSERT INTO read_cues(
                   care_mark_id, term, normalized_term, weight, status,
                   created_at, updated_at, last_touched_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(care_mark_id, normalized_term) DO UPDATE SET
                   term = excluded.term,
                   weight = excluded.weight,
                   status = excluded.status,
                   updated_at = excluded.updated_at,
                   last_touched_at = excluded.last_touched_at''',
            (
                care_mark_id, term, normalized_term, weight, status,
                now, now, now,
            ),
        )
        await self.database.connection.commit()
        cue = await self.get_by_key(care_mark_id, normalized_term)
        if cue is None:
            raise RuntimeError('read cue upsert did not return a row')
        return cue

    async def get(self, read_cue_id: int) -> Optional[ReadCue]:
        row = await (await self.database.connection.execute(
            'SELECT * FROM read_cues WHERE id = ?', (read_cue_id,)
        )).fetchone()
        return self._model(row) if row else None

    async def get_by_key(
        self, care_mark_id: int, normalized_term: str
    ) -> Optional[ReadCue]:
        row = await (await self.database.connection.execute(
            '''SELECT * FROM read_cues
               WHERE care_mark_id = ? AND normalized_term = ?''',
            (care_mark_id, normalized_term),
        )).fetchone()
        return self._model(row) if row else None

    async def list_for_mark(
        self,
        care_mark_id: int,
        statuses: Optional[Iterable[str]] = None,
        limit: int = 20,
    ) -> List[ReadCue]:
        parameters = [care_mark_id]
        status_clause = ''
        if statuses is not None:
            selected = tuple(dict.fromkeys(statuses))
            if not selected:
                return []
            placeholders = ','.join('?' for _ in selected)
            status_clause = f' AND status IN ({placeholders})'
            parameters.extend(selected)
        parameters.append(max(1, min(int(limit), 100)))
        rows = await (await self.database.connection.execute(
            f'''SELECT * FROM read_cues
                WHERE care_mark_id = ?{status_clause}
                ORDER BY weight DESC, id DESC LIMIT ?''',
            tuple(parameters),
        )).fetchall()
        return [self._model(row) for row in rows]

    async def delete(self, read_cue_id: int) -> bool:
        cursor = await self.database.connection.execute(
            'DELETE FROM read_cues WHERE id = ?', (read_cue_id,)
        )
        await self.database.connection.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _model(row: aiosqlite.Row) -> ReadCue:
        return ReadCue(**dict(row))
