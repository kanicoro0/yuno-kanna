from typing import Iterable, List, Optional

from yuno.attention.models import AttentionItem
from yuno.attention.repository import AttentionRepository


class AttentionService:
    def __init__(self, repository: AttentionRepository):
        self.repository = repository

    async def create_open(
        self, stream_id: int, text: str, source_message_id: Optional[int] = None,
        memory_mark_id: Optional[int] = None, rank: float = 0.5,
    ) -> AttentionItem:
        return await self.repository.create(
            stream_id, text, source_message_id, memory_mark_id, rank
        )

    async def touch_many(
        self, stream_id: int, public_ids: Iterable[str]
    ) -> List[AttentionItem]:
        touched = []
        for public_id in list(dict.fromkeys(public_ids))[:8]:
            current = await self.repository.get_by_public_id(public_id)
            if current and current.stream_id == stream_id and current.status == "open":
                item = await self.repository.touch(public_id)
                if item:
                    touched.append(item)
        return touched

    async def close(self, public_id: str) -> Optional[AttentionItem]:
        return await self.repository.close(public_id)

    async def hide(self, public_id: str) -> Optional[AttentionItem]:
        return await self.repository.hide(public_id)

    async def reopen(self, public_id: str) -> Optional[AttentionItem]:
        return await self.repository.reopen(public_id)

    async def references_for_stream(
        self, stream_id: int, limit: int = 8, public_ids: Optional[Iterable[str]] = None
    ) -> List[AttentionItem]:
        items = await self.repository.list_open_for_stream(stream_id, limit)
        if public_ids is None:
            return items
        wanted = set(public_ids)
        return [item for item in items if item.public_id in wanted]
