from dataclasses import dataclass
import re
from typing import List, Sequence, Tuple

from yuno.notebook.records import Note
from yuno.notebook.storage import NotebookStorage


@dataclass(frozen=True)
class NoteCandidate:
    note: Note
    score: float
    matched_by: List[str]
    retrieval_reason: str


def _terms(text: str) -> List[str]:
    return [term.casefold() for term in re.findall(r"[\w\-]{2,}", text)][:40]


class NotebookRetriever:
    """Lexical pre-retrieval. Semantic/vector retrieval can join candidates here later."""

    def __init__(self, storage: NotebookStorage, limit: int = 12):
        self.storage = storage
        self.limit = limit

    async def retrieve(
        self,
        text: str,
        scopes: Sequence[str],
        context: str,
        tag_hints: Sequence[str] = (),
        active_note_ids: Sequence[str] = (),
        suppressed_note_ids: Sequence[str] = (),
    ) -> List[NoteCandidate]:
        notes = await self.storage.list_active(list(scopes))
        suppressed = set(suppressed_note_ids)
        notes = [note for note in notes if note.id not in suppressed]
        terms = set(_terms(text))
        hints = {tag.casefold() for tag in tag_hints}
        ranked: List[Tuple[float, str, NoteCandidate]] = []

        for note in notes:
            if note.contexts and context not in note.contexts:
                continue
            matched = [f"scope:{note.scope.split(':', 1)[0]}"]
            score = note.weight * 0.25
            if note.contexts:
                matched.append(f"context:{context}")
                score += 0.5
            if "always" in note.routes:
                matched.append("always")
                score += 3.0
            tag_matches = sorted(set(note.tags) & (terms | hints))
            if tag_matches and "tag" in note.routes:
                matched.extend(f"tag:{tag}" for tag in tag_matches)
                score += 1.5 * len(tag_matches)
            keyword_matches = sorted(term for term in terms if term in note.content.casefold())
            if keyword_matches and "keyword" in note.routes:
                matched.extend(f"keyword:{term}" for term in keyword_matches[:3])
                score += min(3, len(keyword_matches))
            if note.id in active_note_ids:
                matched.append("mind:active")
                score += 4.0
            if len(matched) == 1 and "always" not in note.routes:
                continue

            reason = ", ".join(matched)
            candidate = NoteCandidate(note, score, matched, reason)
            ranked.append((score, note.updated_at, candidate))

        ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [row[2] for row in ranked[: self.limit]]
