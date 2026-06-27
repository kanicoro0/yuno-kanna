from dataclasses import replace
from typing import Any, Dict, List, Optional

from yuno.actions.schema import ActionPlan, ExecutionResult, PendingCommit
from yuno.memory.records import (
    ALLOWED_CONTEXTS, ALLOWED_ROUTES, ALLOWED_STATES, MemoryRecord, utc_now,
)
from yuno.memory.retrieval import RetrievalCandidate
from yuno.memory.service import MemoryService
from yuno.memory.storage import MemoryStorage


RESERVED_REACTIONS = {"📌", "📝", "🗑️", "🏷️"}
# Automatic rewrite cannot smuggle a delete through a state change.
EDITABLE_FIELDS = {"content", "routes", "contexts", "weight", "tags"}


class ActionExecutor:
    def __init__(
        self,
        storage: MemoryStorage,
        memory_service: Optional[MemoryService] = None,
        speaker_memory_limit: int = 6,
    ):
        self.storage = storage
        self.memory_service = memory_service
        self.speaker_memory_limit = speaker_memory_limit

    async def prepare(
        self,
        plan: ActionPlan,
        candidates: List[RetrievalCandidate],
        allowed_scopes: List[str],
    ) -> ExecutionResult:
        by_id = {candidate.record.id: candidate for candidate in candidates}
        if plan.memory_hints:
            selected = [
                by_id[hint.id].record
                for hint in plan.memory_hints
                if hint.use != "no" and hint.id in by_id
            ]
        else:
            selected = [candidate.record for candidate in candidates]
        selected = selected[: self.speaker_memory_limit]

        speak_actions = [item for item in plan.candidate_actions if item.type == "speak"]
        brief = "\n".join(item.brief for item in speak_actions if item.brief).strip()
        pending: List[PendingCommit] = []
        reactions: List[str] = []
        rejected: List[str] = []

        for action in plan.candidate_actions:
            if action.type == "record":
                try:
                    pending.append(await self._validate_record(action, allowed_scopes))
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
            selected_memories=selected,
            pending_commits=pending,
            reactions=reactions,
            rejected_actions=rejected,
        )

    async def _validate_record(self, action: Any, allowed_scopes: List[str]) -> PendingCommit:
        if action.record_action not in {"add", "rewrite", "delete"}:
            raise ValueError("record action rejected: invalid action")
        if action.scope not in allowed_scopes:
            raise ValueError("record action rejected: scope is not available to this message")

        if action.record_action == "add":
            now = utc_now()
            record = replace(MemoryRecord.from_dict({
                **action.data,
                "scope": action.scope,
                "created_at": now,
                "updated_at": now,
                "state": "active",
            }), id="")
            record.validate()
            active = await self.storage.list_active([record.scope])
            normalized = record.content.casefold().strip()
            if any(item.content.casefold().strip() == normalized for item in active):
                raise ValueError("record action rejected: duplicate content in scope")
            return PendingCommit("add", action.scope, record=record)

        target = await self.storage.get_by_id(action.target_id)
        if target is None or target.state != "active":
            raise ValueError("record action rejected: target does not exist")
        if target.scope != action.scope or target.scope not in allowed_scopes:
            raise ValueError("record action rejected: target scope mismatch")
        if action.record_action == "delete":
            return PendingCommit("delete", action.scope, target_id=target.id)

        changes = {key: value for key, value in action.data.items() if key in EDITABLE_FIELDS}
        if not changes:
            raise ValueError("record action rejected: rewrite has no editable fields")
        candidate = MemoryRecord.from_dict({**target.to_dict(), **changes})
        candidate = replace(candidate, id=target.id, scope=target.scope, created_at=target.created_at)
        candidate.validate()
        active = await self.storage.list_active([target.scope])
        normalized = candidate.content.casefold().strip()
        if any(item.id != target.id and item.content.casefold().strip() == normalized for item in active):
            raise ValueError("record action rejected: duplicate content in scope")
        return PendingCommit("rewrite", action.scope, target_id=target.id, changes=changes)

    async def commit(
        self,
        pending: List[PendingCommit],
        actor_user_id: str = "system",
        source: str = "planner_commit",
    ) -> List[str]:
        """Apply validated actions only after Discord send succeeds."""
        reactions: List[str] = []
        for item in pending:
            if item.action == "add" and item.record:
                if self.memory_service:
                    await self.memory_service.add(item.record, actor_user_id, source)
                else:
                    await self.storage.create(item.record)
            elif item.action == "delete":
                deleted = (
                    await self.memory_service.delete(item.target_id, actor_user_id, source)
                    if self.memory_service
                    else await self.storage.mark_deleted(item.target_id)
                )
                if deleted is None:
                    continue
            elif item.action == "rewrite":
                if self.memory_service:
                    updated = await self.memory_service.rewrite(
                        item.target_id, item.changes, actor_user_id, source
                    )
                    if updated is None:
                        continue
                else:
                    target = await self.storage.get_by_id(item.target_id)
                    if target is None or target.state != "active":
                        continue
                    updated = MemoryRecord.from_dict({**target.to_dict(), **item.changes})
                    await self.storage.upsert(updated)
            else:
                continue
            reactions.append(self._system_reaction(item))
        return reactions

    @staticmethod
    def _system_reaction(item: PendingCommit) -> str:
        if item.scope.startswith(("guild:", "channel:")):
            return "🏷️"
        return {"add": "📌", "rewrite": "📝", "delete": "🗑️"}[item.action]
