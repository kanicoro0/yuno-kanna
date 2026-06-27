from typing import Any, Dict, List

from yuno.memory.records import MemoryRecord
from yuno.memory.retrieval import RetrievalCandidate


def planner_memory_view(candidates: List[RetrievalCandidate]) -> List[Dict[str, Any]]:
    return [{
        "id": item.record.id,
        "scope": item.record.scope,
        "content": item.record.content,
        "routes": item.record.routes,
        "tags": item.record.tags,
        "weight": item.record.weight,
        "score": round(item.score, 2),
        "matched_by": item.matched_by,
        "retrieval_reason": item.retrieval_reason,
    } for item in candidates]


def speaker_memory_view(records: List[MemoryRecord]) -> List[Dict[str, Any]]:
    return [{"id": record.id, "content": record.content, "scope": record.scope, "tags": record.tags}
            for record in records]
