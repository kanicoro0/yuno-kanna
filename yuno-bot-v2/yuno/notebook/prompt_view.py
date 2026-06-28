from typing import Any, Dict, List

from yuno.notebook.records import Note
from yuno.notebook.retrieval import NoteCandidate


def planner_note_view(candidates: List[NoteCandidate]) -> List[Dict[str, Any]]:
    return [{
        "note_id": item.note.id,
        "scope": item.note.scope,
        "content": item.note.content,
        "routes": item.note.routes,
        "tags": item.note.tags,
        "weight": item.note.weight,
        "score": round(item.score, 2),
        "matched_by": item.matched_by,
        "retrieval_reason": item.retrieval_reason,
    } for item in candidates]


def speaker_note_view(records: List[Note]) -> List[Dict[str, Any]]:
    return [{"note_id": record.id, "content": record.content, "scope": record.scope, "tags": record.tags}
            for record in records]
