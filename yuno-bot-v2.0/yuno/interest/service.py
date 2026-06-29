import unicodedata
from typing import Iterable, List, Optional

from yuno.interest.models import InterestTerm
from yuno.interest.repository import InterestRepository


def normalize_term(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


class InterestService:
    def __init__(self, repository: InterestRepository):
        self.repository = repository

    async def update_from_care(
        self, stream_id: int, updates: Iterable[object]
    ) -> List[InterestTerm]:
        result = []
        for update in list(updates)[:5]:
            term = normalize_term(str(getattr(update, "term", "")))[:80]
            if not term:
                continue
            weight = max(0.2, min(0.6, float(getattr(update, "weight", 0.3))))
            result.append(await self.repository.upsert_term(
                stream_id, term, weight, "care_reader"
            ))
        return result

    async def list_for_care(self, stream_id: int, limit: int = 8) -> List[InterestTerm]:
        return await self.repository.list_active_for_stream(stream_id, limit)

    async def references_for_stream(self, stream_id: int, limit: int = 8) -> List[InterestTerm]:
        return await self.repository.list_active_for_stream(stream_id, limit)

    async def hide(self, public_id: str) -> Optional[InterestTerm]:
        return await self.repository.hide(public_id)
