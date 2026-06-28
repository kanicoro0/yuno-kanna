from dataclasses import replace
from typing import Any, Dict, List, Optional

from yuno.actions.schema import ActionPlan, ExecutionResult, PendingNoteCommit
from yuno.notebook.records import (
    ALLOWED_CONTEXTS, ALLOWED_ROUTES, ALLOWED_STATES, Note, utc_now,
)
from yuno.notebook.retrieval import NoteCandidate
from yuno.notebook.service import Notebook
from yuno.notebook.storage import NotebookStorage


RESERVED_REACTIONS = {"📌", "📝", "🗑️", "🏷️"}
# Automatic rewrite cannot smuggle a delete through a state change.
EDITABLE_FIELDS = {"content", "routes", "contexts", "weight", "tags"}


class ActionExecutor:
    def __init__(
        self,
        storage: NotebookStorage,
        notebook: Optional[Notebook] = None,
        speaker_note_limit: int = 6,
    ):
        self.storage = storage
        self.notebook = notebook
        self.speaker_note_limit = speaker_note_limit

    async def prepare(
        self,
        plan: ActionPlan,
        candidates: List[NoteCandidate],
        allowed_scopes: List[str],
    ) -> ExecutionResult:
        by_id = {candidate.note.id: candidate for candidate in candidates}
        if plan.note_hints:
            selected = [
                by_id[hint.note_id].note
                for hint in plan.note_hints
                if hint.use != "no" and hint.note_id in by_id
            ]
        else:
            selected = [candidate.note for candidate in candidates]
        selected = selected[: self.speaker_note_limit]

        speak_actions = [item for item in plan.candidate_actions if item.type == "speak"]
        brief = "\n".join(item.brief for item in speak_actions if item.brief).strip()
        pending: List[PendingNoteCommit] = []
        reactions: List[str] = []
        rejected: List[str] = []

        for action in plan.candidate_actions:
            if action.type == "note":
                try:
                    pending.append(await self._validate_note(action, allowed_scopes))
                except ValueError as error:
                    rejected.append(str(error))
            elif action.type == "react":
                if action.emoji and action.emoji not in RESERVED_REACTIONS:
                    reactions.append(action.emoji)
                elif action.emoji:
                    rejected.append("reserved system reaction rejected")

        return ExecutionResult(
            should_speak=bool(speak_actions),
            speaker_brief=brief,
            selected_notes=selected,
            pending_commits=pending,
            reactions=reactions,
            rejected_actions=rejected,
        )

    async def _validate_note(self, action: Any, allowed_scopes: List[str]) -> PendingNoteCommit:
        if action.note_action not in {"add", "rewrite", "delete"}:
            raise ValueError("note action rejected: invalid action")
        if action.scope not in allowed_scopes:
            raise ValueError("note action rejected: scope is not available to this message")

        if action.note_action == "add":
            now = utc_now()
            note = replace(Note.from_dict({
                **action.data,
                "scope": action.scope,
                "created_at": now,
                "updated_at": now,
                "state": "active",
            }), id="")
            note.validate()
            active = await self.storage.list_active([note.scope])
            normalized = note.content.casefold().strip()
            if any(item.content.casefold().strip() == normalized for item in active):
                raise ValueError("note action rejected: duplicate content in scope")
            return PendingNoteCommit("add", action.scope, note=note)

        target = await self.storage.get_by_id(action.target_note_id)
        if target is None or target.state != "active":
            raise ValueError("note action rejected: target does not exist")
        if target.scope != action.scope or target.scope not in allowed_scopes:
            raise ValueError("note action rejected: target scope mismatch")
        if action.note_action == "delete":
            return PendingNoteCommit("delete", action.scope, target_note_id=target.id)

        changes = {key: value for key, value in action.data.items() if key in EDITABLE_FIELDS}
        if not changes:
            raise ValueError("note action rejected: rewrite has no editable fields")
        candidate = Note.from_dict({**target.to_dict(), **changes})
        candidate = replace(candidate, id=target.id, scope=target.scope, created_at=target.created_at)
        candidate.validate()
        active = await self.storage.list_active([target.scope])
        normalized = candidate.content.casefold().strip()
        if any(item.id != target.id and item.content.casefold().strip() == normalized for item in active):
            raise ValueError("note action rejected: duplicate content in scope")
        return PendingNoteCommit("rewrite", action.scope, target_note_id=target.id, changes=changes)

    async def commit(
        self,
        pending: List[PendingNoteCommit],
        actor_user_id: str = "system",
        source: str = "planner_commit",
    ) -> List[str]:
        """Apply validated actions only after Discord send succeeds."""
        reactions: List[str] = []
        for item in pending:
            if item.action == "add" and item.note:
                if self.notebook:
                    await self.notebook.add(item.note, actor_user_id, source)
                else:
                    await self.storage.create(item.note)
            elif item.action == "delete":
                deleted = (
                    await self.notebook.delete(item.target_note_id, actor_user_id, source)
                    if self.notebook
                    else await self.storage.mark_deleted(item.target_note_id)
                )
                if deleted is None:
                    continue
            elif item.action == "rewrite":
                if self.notebook:
                    updated = await self.notebook.rewrite(
                        item.target_note_id, item.changes, actor_user_id, source
                    )
                    if updated is None:
                        continue
                else:
                    target = await self.storage.get_by_id(item.target_note_id)
                    if target is None or target.state != "active":
                        continue
                    updated = Note.from_dict({**target.to_dict(), **item.changes})
                    await self.storage.upsert(updated)
            else:
                continue
            reactions.append(self._system_reaction(item))
        return reactions

    @staticmethod
    def _system_reaction(item: PendingNoteCommit) -> str:
        if item.scope.startswith(("guild:", "channel:")):
            return "🏷️"
        return {"add": "📌", "rewrite": "📝", "delete": "🗑️"}[item.action]
