from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from yuno.notebook.records import utc_now


def _strings(value: Any, limit: int, item_limit: int = 300) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:item_limit] for item in value if str(item).strip()][:limit]


@dataclass
class MindUpdate:
    summary: str = ""
    open_questions: List[str] = field(default_factory=list)
    active_note_ids: List[str] = field(default_factory=list)
    suppressed_note_ids: List[str] = field(default_factory=list)
    tone_hint: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "MindUpdate":
        if not isinstance(data, dict):
            return cls()
        return cls(
            summary=str(data.get("summary", "")).strip()[:1000],
            open_questions=_strings(data.get("open_questions"), 5),
            active_note_ids=[value for value in _strings(data.get("active_note_ids"), 10, 80)
                             if value.startswith("note_")],
            suppressed_note_ids=[value for value in _strings(data.get("suppressed_note_ids"), 10, 80)
                                 if value.startswith("note_")],
            tone_hint=str(data.get("tone_hint", "")).strip()[:300],
        )

    def is_empty(self) -> bool:
        return not any((self.summary, self.open_questions, self.active_note_ids,
                        self.suppressed_note_ids, self.tone_hint))


@dataclass
class MindState:
    scope: str
    updated_at: str = field(default_factory=utc_now)
    summary: str = ""
    open_questions: List[str] = field(default_factory=list)
    active_note_ids: List[str] = field(default_factory=list)
    suppressed_note_ids: List[str] = field(default_factory=list)
    tone_hint: str = ""
    source_message_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MindState":
        update = MindUpdate.from_dict(data)
        return cls(
            scope=str(data.get("scope", "")),
            updated_at=str(data.get("updated_at") or utc_now()),
            summary=update.summary,
            open_questions=update.open_questions,
            active_note_ids=update.active_note_ids,
            suppressed_note_ids=update.suppressed_note_ids,
            tone_hint=update.tone_hint,
            source_message_id=str(data["source_message_id"]) if data.get("source_message_id") else None,
        )

    @classmethod
    def from_update(cls, scope: str, update: MindUpdate, source_message_id: str) -> "MindState":
        return cls(scope=scope, summary=update.summary, open_questions=update.open_questions,
                   active_note_ids=update.active_note_ids,
                   suppressed_note_ids=update.suppressed_note_ids,
                   tone_hint=update.tone_hint, source_message_id=source_message_id)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
