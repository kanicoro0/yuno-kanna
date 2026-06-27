from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from yuno.memory.records import MemoryRecord


LEVELS = {"high", "medium", "low"}
ACTION_TYPES = {"speak", "record", "react", "noop"}
RECORD_ACTIONS = {"add", "rewrite", "delete"}
NEXT_CALL_TYPES = {"none", "followup", "repair", "second_thought"}


@dataclass
class Reading:
    main_point: str = ""
    subtext: str = ""
    do_not_flatten: List[str] = field(default_factory=list)


@dataclass
class CandidateAction:
    type: str
    confidence: str = "low"
    brief: str = ""
    emoji: str = ""
    record_action: str = ""
    scope: str = ""
    target_id: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateAction":
        action_type = str(data.get("type", "noop"))
        return cls(
            type=action_type if action_type in ACTION_TYPES else "noop",
            confidence=str(data.get("confidence", "low")),
            brief=str(data.get("brief", ""))[:1000],
            emoji=str(data.get("emoji", ""))[:16],
            record_action=str(data.get("record_action", data.get("action", ""))),
            scope=str(data.get("scope", "")),
            target_id=str(data.get("target_id", "")),
            data=data.get("data", {}) if isinstance(data.get("data"), dict) else {},
        )


@dataclass
class MemoryHint:
    id: str
    relevance: str = "low"
    use: str = "possible"
    reason: str = ""


@dataclass
class SpeakerGuidance:
    depth: str = "medium"
    style: str = "natural"
    avoid: List[str] = field(default_factory=list)


@dataclass
class ActionPlan:
    reading: Reading
    attention: Dict[str, Dict[str, str]]
    memory_hints: List[MemoryHint]
    candidate_actions: List[CandidateAction]
    speaker_guidance: SpeakerGuidance

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionPlan":
        raw_reading = data.get("reading", {}) if isinstance(data.get("reading"), dict) else {}
        raw_hints = data.get("memory_hints", [])
        raw_actions = data.get("candidate_actions", [])
        raw_guidance = data.get("speaker_guidance", {}) if isinstance(data.get("speaker_guidance"), dict) else {}
        attention = data.get("attention", {}) if isinstance(data.get("attention"), dict) else {}
        return cls(
            reading=Reading(
                main_point=str(raw_reading.get("main_point", ""))[:1000],
                subtext=str(raw_reading.get("subtext", ""))[:1000],
                do_not_flatten=[str(item)[:300] for item in raw_reading.get("do_not_flatten", []) if isinstance(item, str)][:10],
            ),
            attention=attention,
            memory_hints=[MemoryHint(
                id=str(item.get("id", "")), relevance=str(item.get("relevance", "low")),
                use=str(item.get("use", "possible")), reason=str(item.get("reason", ""))[:500],
            ) for item in raw_hints if isinstance(item, dict)][:20],
            candidate_actions=[CandidateAction.from_dict(item) for item in raw_actions if isinstance(item, dict)][:10],
            speaker_guidance=SpeakerGuidance(
                depth=str(raw_guidance.get("depth", "medium")),
                style=str(raw_guidance.get("style", "natural")),
                avoid=[str(item)[:300] for item in raw_guidance.get("avoid", []) if isinstance(item, str)][:10],
            ),
        )


@dataclass
class PendingCommit:
    action: str
    scope: str
    record: Optional[MemoryRecord] = None
    target_id: str = ""
    changes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    should_speak: bool
    speaker_brief: str
    selected_memories: List[MemoryRecord]
    pending_commits: List[PendingCommit]
    reactions: List[str]
    rejected_actions: List[str] = field(default_factory=list)


@dataclass
class NextCall:
    needed: bool = False
    type: str = "none"
    reason: str = ""
    brief: str = ""


@dataclass
class SpeakerOutput:
    reply: str
    next_call: NextCall = field(default_factory=NextCall)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpeakerOutput":
        raw_next = data.get("next_call", {}) if isinstance(data.get("next_call"), dict) else {}
        call_type = str(raw_next.get("type", "none"))
        if call_type not in NEXT_CALL_TYPES:
            call_type = "none"
        return cls(
            reply=str(data.get("reply", "")).strip(),
            next_call=NextCall(
                needed=bool(raw_next.get("needed", False)) and call_type != "none",
                type=call_type,
                reason=str(raw_next.get("reason", ""))[:500],
                brief=str(raw_next.get("brief", ""))[:1000],
            ),
        )
