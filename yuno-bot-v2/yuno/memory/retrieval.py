from dataclasses import dataclass
import re
from typing import List, Sequence, Tuple

from yuno.memory.records import MemoryRecord
from yuno.memory.storage import MemoryStorage


@dataclass(frozen=True)
class RetrievalCandidate:
    record: MemoryRecord
    score: float
    matched_by: List[str]
    retrieval_reason: str


def _terms(text: str) -> List[str]:
    return [term.casefold() for term in re.findall(r"[\w\-]{2,}", text)][:40]


class MemoryRetriever:
    """Lexical pre-retrieval. Semantic/vector retrieval can join candidates here later."""

    def __init__(self, storage: MemoryStorage, limit: int = 12):
        self.storage = storage
        self.limit = limit

    async def retrieve(
        self,
        text: str,
        scopes: Sequence[str],
        context: str,
        tag_hints: Sequence[str] = (),
    ) -> List[RetrievalCandidate]:
        records = await self.storage.list_active(list(scopes))
        terms = set(_terms(text))
        hints = {tag.casefold() for tag in tag_hints}
        ranked: List[Tuple[float, str, RetrievalCandidate]] = []

        for record in records:
            if record.contexts and context not in record.contexts:
                continue
            matched = [f"scope:{record.scope.split(':', 1)[0]}"]
            score = record.weight * 0.25
            if record.contexts:
                matched.append(f"context:{context}")
                score += 0.5
            if "always" in record.routes:
                matched.append("always")
                score += 3.0
            tag_matches = sorted(set(record.tags) & (terms | hints))
            if tag_matches and "tag" in record.routes:
                matched.extend(f"tag:{tag}" for tag in tag_matches)
                score += 1.5 * len(tag_matches)
            keyword_matches = sorted(term for term in terms if term in record.content.casefold())
            if keyword_matches and "keyword" in record.routes:
                matched.extend(f"keyword:{term}" for term in keyword_matches[:3])
                score += min(3, len(keyword_matches))
            if len(matched) == 1 and "always" not in record.routes:
                continue

            reason = ", ".join(matched)
            candidate = RetrievalCandidate(record, score, matched, reason)
            ranked.append((score, record.updated_at, candidate))

        ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [row[2] for row in ranked[: self.limit]]
