import unicodedata
from typing import Iterable, List, Optional

from yuno.read_cues.models import ReadCue
from yuno.read_cues.repository import ReadCueRepository


READ_CUE_STATUSES = frozenset({'active', 'sleeping', 'hidden'})


def normalize_term(value: str) -> str:
    return unicodedata.normalize('NFKC', value).casefold().strip()


class ReadCueService:
    def __init__(self, repository: ReadCueRepository):
        self.repository = repository

    async def upsert(
        self,
        care_mark_id: int,
        term: str,
        weight: float = 0.3,
        status: str = 'active',
    ) -> ReadCue:
        selected_term = term.strip()[:80]
        normalized = normalize_term(selected_term)
        if not normalized:
            raise ValueError('read cue term must not be empty')
        self._validate_status(status)
        return await self.repository.upsert(
            care_mark_id,
            selected_term,
            normalized[:80],
            max(0.0, min(1.0, float(weight))),
            status,
        )

    async def get(self, read_cue_id: int) -> Optional[ReadCue]:
        return await self.repository.get(read_cue_id)

    async def list_for_mark(
        self,
        care_mark_id: int,
        statuses: Optional[Iterable[str]] = None,
        limit: int = 20,
    ) -> List[ReadCue]:
        if statuses is not None:
            selected = tuple(statuses)
            for status in selected:
                self._validate_status(status)
            statuses = selected
        return await self.repository.list_for_mark(care_mark_id, statuses, limit)

    async def set_status(
        self, read_cue_id: int, status: str
    ) -> Optional[ReadCue]:
        self._validate_status(status)
        cue = await self.repository.get(read_cue_id)
        if cue is None:
            return None
        return await self.repository.upsert(
            cue.care_mark_id,
            cue.term,
            cue.normalized_term,
            cue.weight,
            status,
        )

    async def delete(self, read_cue_id: int) -> bool:
        return await self.repository.delete(read_cue_id)

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in READ_CUE_STATUSES:
            raise ValueError('invalid read cue status')
