from typing import Iterable, List, Optional

from yuno.care_marks.models import CareMark
from yuno.care_marks.repository import CareMarkRepository


CARE_MARK_STATUSES = {
    'memory': frozenset({'draft', 'active', 'hidden'}),
    'attention': frozenset({'open', 'closed', 'hidden'}),
}


class CareMarkService:
    def __init__(self, repository: CareMarkRepository):
        self.repository = repository

    async def create(
        self,
        stream_id: int,
        kind: str,
        status: str,
        text: str,
        source_message_id: Optional[int] = None,
    ) -> CareMark:
        selected_text = self._text(text)
        self._validate_status(kind, status)
        return await self.repository.create(
            stream_id, source_message_id, kind, status, selected_text
        )

    async def get_by_public_id(self, public_id: str) -> Optional[CareMark]:
        return await self.repository.get_by_public_id(public_id)

    async def list_for_stream(
        self,
        stream_id: int,
        kinds: Iterable[str] = ('memory', 'attention'),
        statuses: Optional[Iterable[str]] = None,
        limit: int = 20,
    ) -> List[CareMark]:
        return await self.repository.list_for_stream(
            stream_id, kinds, statuses, limit
        )

    async def list_for_source(
        self,
        stream_id: int,
        source_message_id: int,
        kind: str,
    ) -> List[CareMark]:
        if kind not in CARE_MARK_STATUSES:
            raise ValueError('invalid care mark kind')
        return await self.repository.list_for_source(
            stream_id, source_message_id, kind
        )

    async def update(
        self,
        public_id: str,
        *,
        status: Optional[str] = None,
        text: Optional[str] = None,
    ) -> Optional[CareMark]:
        mark = await self.repository.get_by_public_id(public_id)
        if mark is None:
            return None
        selected_status = status if status is not None else mark.status
        selected_text = self._text(text) if text is not None else mark.text
        self._validate_status(mark.kind, selected_status)
        return await self.repository.update(
            mark.id, status=selected_status, text=selected_text
        )

    async def touch(self, public_id: str) -> Optional[CareMark]:
        mark = await self.repository.get_by_public_id(public_id)
        return await self.repository.touch(mark.id) if mark else None

    async def delete(self, public_id: str) -> bool:
        mark = await self.repository.get_by_public_id(public_id)
        return await self.repository.delete(mark.id) if mark else False

    @staticmethod
    def _validate_status(kind: str, status: str) -> None:
        if kind not in CARE_MARK_STATUSES:
            raise ValueError('invalid care mark kind')
        if status not in CARE_MARK_STATUSES[kind]:
            raise ValueError(f'invalid status for {kind} care mark')

    @staticmethod
    def _text(value: str) -> str:
        selected = value.strip()[:500]
        if not selected:
            raise ValueError('care mark text must not be empty')
        return selected
