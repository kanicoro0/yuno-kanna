from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


ALLOWED_ROUTES = {"always", "semantic", "keyword", "tag", "explicit"}
ALLOWED_CONTEXTS = {"dm", "mention", "nonmention", "prefix", "command"}
ALLOWED_STATES = {"active", "deleted"}
PREFERRED_TAGS = {
    "preference", "fact", "behavior", "policy", "project", "note", "correction",
    "tone", "reply_style", "reply_length", "confirmation", "nonmention",
    "server_behavior", "channel_behavior", "dm_behavior", "memory_design",
    "action_plan", "retrieval", "planner", "speaker", "executor", "commit",
    "discord_bot", "yuno_v2", "writing", "art", "philosophy", "app_design", "code",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_memory_id() -> str:
    """Random fallback for malformed/imported records; normal creation uses MemoryStorage.create."""
    return "mem_" + uuid.uuid4().hex[:12]


def _strings(value: Any, allowed: Optional[set] = None, limit: int = 20) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        item = item.strip().lower()
        if item and item not in result and (allowed is None or item in allowed):
            result.append(item)
    return result[:limit]


@dataclass
class MemoryRecord:
    id: str
    scope: str
    content: str
    routes: List[str]
    contexts: List[str]
    weight: int
    tags: List[str]
    state: str = "active"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    last_used_at: Optional[str] = None
    use_count: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRecord":
        weight = data.get("weight", 3)
        try:
            weight = max(1, min(5, int(weight)))
        except (TypeError, ValueError):
            weight = 3
        state = data.get("state", "active")
        if state not in ALLOWED_STATES:
            state = "active"
        return cls(
            id=str(data.get("id") or new_memory_id()),
            scope=str(data.get("scope", "")),
            content=str(data.get("content", "")).strip(),
            routes=_strings(data.get("routes"), ALLOWED_ROUTES) or ["explicit"],
            contexts=_strings(data.get("contexts"), ALLOWED_CONTEXTS),
            weight=weight,
            tags=_strings(data.get("tags"), limit=5),
            state=state,
            created_at=str(data.get("created_at") or utc_now()),
            updated_at=str(data.get("updated_at") or utc_now()),
            last_used_at=data.get("last_used_at"),
            use_count=max(0, int(data.get("use_count", 0) or 0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def validate(self) -> None:
        if not self.scope.startswith(("user:", "guild:", "channel:")):
            raise ValueError("invalid memory scope")
        if not self.content or len(self.content) > 1000:
            raise ValueError("memory content must contain 1-1000 characters")
        if not self.routes or any(route not in ALLOWED_ROUTES for route in self.routes):
            raise ValueError("invalid memory routes")
        if any(context not in ALLOWED_CONTEXTS for context in self.contexts):
            raise ValueError("invalid memory contexts")
        if not 1 <= self.weight <= 5:
            raise ValueError("memory weight must be between 1 and 5")
        if len(self.tags) > 5:
            raise ValueError("memory tags must contain at most five values")
        if self.state not in ALLOWED_STATES:
            raise ValueError("invalid memory state")
