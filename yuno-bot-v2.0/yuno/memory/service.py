from typing import Iterable, List, Optional

from yuno.memory.models import MemoryMark
from yuno.memory.repository import MemoryMarkRepository


class MemoryMarkService:
    def __init__(self, repository: MemoryMarkRepository):
        self.repository = repository

    async def create_pending_from_care(
        self, stream_id: int, source_message_id: int, content: str,
        kind: str = "pin", confidence: float = 0.5, status: str = "pending",
    ) -> MemoryMark:
        return await self.repository.create(
            stream_id, source_message_id, kind, status, content, confidence, "care_reader"
        )

    async def activate(self, public_id: str) -> Optional[MemoryMark]:
        return await self.repository.activate(public_id)

    async def hide(self, public_id: str) -> Optional[MemoryMark]:
        return await self.repository.hide(public_id)

    async def restore_to_pending(self, public_id: str) -> Optional[MemoryMark]:
        return await self.repository.restore_to_pending(public_id)

    async def references_for_stream(
        self, stream_id: int, limit: int = 8, public_ids: Optional[Iterable[str]] = None
    ) -> List[MemoryMark]:
        marks = await self.repository.list_for_stream(stream_id, ("active",), limit)
        if public_ids is None:
            return marks
        wanted = set(public_ids)
        return [mark for mark in marks if mark.public_id in wanted]
