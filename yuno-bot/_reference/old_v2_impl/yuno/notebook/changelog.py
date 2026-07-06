import asyncio
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
import uuid

from yuno.infra.json_store import JsonStore
from yuno.notebook.records import utc_now


@dataclass
class NoteChange:
    change_id: str
    timestamp: str
    actor_user_id: str
    source: str
    action: str
    note_id: str
    scope: str
    before: Optional[Dict[str, Any]]
    after: Optional[Dict[str, Any]]
    undo_of: Optional[str] = None

    @classmethod
    def create(
        cls,
        *,
        actor_user_id: str,
        source: str,
        action: str,
        note_id: str,
        scope: str,
        before: Optional[Dict[str, Any]],
        after: Optional[Dict[str, Any]],
        undo_of: Optional[str] = None,
    ) -> "NoteChange":
        return cls(
            change_id="chg_" + uuid.uuid4().hex[:12],
            timestamp=utc_now(),
            actor_user_id=str(actor_user_id),
            source=source,
            action=action,
            note_id=note_id,
            scope=scope,
            before=before,
            after=after,
            undo_of=undo_of,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NoteChange":
        return cls(
            change_id=str(data.get("change_id", "")),
            timestamp=str(data.get("timestamp", "")),
            actor_user_id=str(data.get("actor_user_id", "")),
            source=str(data.get("source", "system")),
            action=str(data.get("action", "rewrite")),
            note_id=str(data.get("note_id", "")),
            scope=str(data.get("scope", "")),
            before=data.get("before") if isinstance(data.get("before"), dict) else None,
            after=data.get("after") if isinstance(data.get("after"), dict) else None,
            undo_of=str(data["undo_of"]) if data.get("undo_of") else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NotebookChangeLog:
    SCHEMA_VERSION = 1

    def __init__(self, store: JsonStore):
        self.store = store
        self._lock = asyncio.Lock()

    async def _load(self) -> List[NoteChange]:
        payload = await self.store.load({"schema_version": 1, "changes": []})
        if not isinstance(payload, dict) or payload.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError("unsupported notebook changelog schema; expected schema_version 1")
        values = payload.get("changes", [])
        if not isinstance(values, list):
            raise ValueError("notebook changelog changes must be a list")
        return [NoteChange.from_dict(item) for item in values if isinstance(item, dict)]

    async def append(self, change: NoteChange) -> NoteChange:
        async with self._lock:
            changes = await self._load()
            changes.append(change)
            await self.store.save({"schema_version": 1, "changes": [item.to_dict() for item in changes]})
        return change

    async def list_scope(self, scope: str) -> List[NoteChange]:
        return [change for change in await self._load() if change.scope == scope]

    async def latest_undoable(self, scope: str, actor_user_id: str) -> Optional[NoteChange]:
        changes = await self._load()
        undone = {change.undo_of for change in changes if change.undo_of}
        for change in reversed(changes):
            if (
                change.scope == scope
                and change.actor_user_id == str(actor_user_id)
                and change.source != "undo"
                and change.action in {"add", "rewrite", "delete"}
                and change.change_id not in undone
            ):
                return change
        return None
