import asyncio
from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

from yuno.notebook.changelog import NoteChange, NotebookChangeLog
from yuno.notebook.records import Note
from yuno.notebook.storage import NotebookStorage


class Notebook:
    """Shared mutation boundary for slash CRUD, Planner commit, and undo."""

    def __init__(self, storage: NotebookStorage, changelog: NotebookChangeLog):
        self.storage = storage
        self.changelog = changelog
        self._mutation_lock = asyncio.Lock()

    @staticmethod
    def _matches_expected(record: Note, expected: Dict[str, Any]) -> bool:
        ignored = {"updated_at", "last_used_at", "use_count"}
        current = {key: value for key, value in record.to_dict().items() if key not in ignored}
        target = {key: value for key, value in expected.items() if key not in ignored}
        return current == target

    async def add(self, record: Note, actor_user_id: str, source: str) -> Note:
        async with self._mutation_lock:
            return await self._add(record, actor_user_id, source)

    async def _add(self, record: Note, actor_user_id: str, source: str) -> Note:
        active = await self.storage.list_active([record.scope])
        normalized = record.content.casefold().strip()
        if any(item.content.casefold().strip() == normalized for item in active):
            raise ValueError("duplicate content in scope")
        saved = await self.storage.create(record)
        await self.changelog.append(NoteChange.create(
            actor_user_id=actor_user_id, source=source, action="add",
            note_id=saved.id, scope=saved.scope, before=None, after=saved.to_dict(),
        ))
        return saved

    async def rewrite(
        self,
        note_id: str,
        changes: Dict[str, Any],
        actor_user_id: str,
        source: str,
    ) -> Optional[Note]:
        async with self._mutation_lock:
            return await self._rewrite(note_id, changes, actor_user_id, source)

    async def _rewrite(
        self,
        note_id: str,
        changes: Dict[str, Any],
        actor_user_id: str,
        source: str,
    ) -> Optional[Note]:
        current = await self.storage.get_by_id(note_id)
        if current is None or current.state != "active":
            return None
        candidate = Note.from_dict({**current.to_dict(), **changes})
        candidate = replace(candidate, id=current.id, scope=current.scope, created_at=current.created_at)
        candidate.validate()
        active = await self.storage.list_active([current.scope])
        normalized = candidate.content.casefold().strip()
        if any(item.id != current.id and item.content.casefold().strip() == normalized for item in active):
            raise ValueError("duplicate content in scope")
        saved = await self.storage.upsert(candidate)
        await self.changelog.append(NoteChange.create(
            actor_user_id=actor_user_id, source=source, action="rewrite",
            note_id=saved.id, scope=saved.scope,
            before=current.to_dict(), after=saved.to_dict(),
        ))
        return saved

    async def delete(
        self, note_id: str, actor_user_id: str, source: str,
    ) -> Optional[Note]:
        async with self._mutation_lock:
            return await self._delete(note_id, actor_user_id, source)

    async def _delete(
        self, note_id: str, actor_user_id: str, source: str,
    ) -> Optional[Note]:
        current = await self.storage.get_by_id(note_id)
        if current is None or current.state != "active":
            return None
        deleted = await self.storage.mark_deleted(note_id)
        if deleted is None:
            return None
        await self.changelog.append(NoteChange.create(
            actor_user_id=actor_user_id, source=source, action="delete",
            note_id=deleted.id, scope=deleted.scope,
            before=current.to_dict(), after=deleted.to_dict(),
        ))
        return deleted

    async def history(self, scope: str) -> List[NoteChange]:
        return list(reversed(await self.changelog.list_scope(scope)))

    async def undo(self, scope: str, actor_user_id: str) -> Optional[Tuple[NoteChange, Note]]:
        async with self._mutation_lock:
            return await self._undo(scope, actor_user_id)

    async def _undo(
        self, scope: str, actor_user_id: str
    ) -> Optional[Tuple[NoteChange, Note]]:
        target = await self.changelog.latest_undoable(scope, actor_user_id)
        if target is None:
            return None
        current = await self.storage.get_by_id(target.note_id)
        if current is None or (
            target.after is not None and not self._matches_expected(current, target.after)
        ):
            raise ValueError("notebook changed after this operation; undo stopped")

        if target.action == "add":
            restored = await self.storage.mark_deleted(target.note_id)
            inverse_action = "delete"
        elif target.action in {"rewrite", "delete"} and target.before:
            restored = await self.storage.upsert(Note.from_dict(target.before))
            inverse_action = "rewrite"
        else:
            raise ValueError("change cannot be undone")
        if restored is None:
            raise ValueError("notebook no longer exists")

        undo_change = NoteChange.create(
            actor_user_id=actor_user_id,
            source="undo",
            action=inverse_action,
            note_id=restored.id,
            scope=scope,
            before=current.to_dict(),
            after=restored.to_dict(),
            undo_of=target.change_id,
        )
        await self.changelog.append(undo_change)
        return target, restored
