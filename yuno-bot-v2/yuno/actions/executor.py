from dataclasses import replace
from typing import Any, Dict, List

from yuno.actions.schema import ActionPlan, ExecutionResult, PendingCommit
from yuno.memory.records import (
    ALLOWED_CONTEXTS, ALLOWED_ROUTES, ALLOWED_STATES, MemoryRecord, new_memory_id, utc_now,
)
from yuno.memory.retrieval import RetrievalCandidate
from yuno.memory.storage import MemoryStorage


RESERVED_REACTIONS = {"📌", "📝", "🗑️", "🏷️"}
# Automatic rewrite cannot smuggle a delete through a state change.
EDITABLE_FIELDS = {"content", "routes", "contexts", "weight", "tags"}


class ActionExecutor:
    def __init__(self, storage: MemoryStorage, speaker_memory_limit: int = 6):
        self.storage = storage
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
            record = MemoryRecord.from_dict({
                **action.data,
                "id": new_memory_id(),
                "scope": action.scope,
                "created_at": now,
                "updated_at": now,
                "state": "active",
            })
            record.validate()
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
        return PendingCommit("rewrite", action.scope, target_id=target.id, changes=changes)

    async def commit(self, pending: List[PendingCommit]) -> List[str]:
        """Apply validated actions only after Discord send succeeds."""
        reactions: List[str] = []
        for item in pending:
            if item.action == "add" and item.record:
                await self.storage.upsert(item.record)
            elif item.action == "delete":
                if await self.storage.mark_deleted(item.target_id) is None:
                    continue
            elif item.action == "rewrite":
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
