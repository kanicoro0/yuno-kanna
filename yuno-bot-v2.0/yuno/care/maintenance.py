from dataclasses import dataclass
from typing import Dict, Optional, Protocol, Sequence, Tuple

from yuno.care_marks.models import CareMark
from yuno.care_marks.service import CareMarkService
from yuno.conversation.repository import ConversationRepository


MAX_MAINTENANCE_MARKS = 20
MAX_MAINTENANCE_MESSAGES = 12
MAX_MAINTENANCE_ACTIONS = 12
MAX_AUTOMATIC_CLOSES = 3

MAINTENANCE_ACTIONS = frozenset({
    'keep',
    'close_attention',
    'merge_attention',
    'rewrite_mark_text',
    'promote_draft_memory',
    'hide_or_ignore_noisy_mark',
})


@dataclass(frozen=True)
class CareMaintenanceMark:
    public_id: str
    kind: str
    status: str
    text: str
    has_source: bool


@dataclass(frozen=True)
class CareMaintenanceMessage:
    role: str
    content: str


@dataclass(frozen=True)
class CareMaintenanceRequest:
    stream_id: int
    care_marks: Tuple[CareMaintenanceMark, ...]
    recent_messages: Tuple[CareMaintenanceMessage, ...]


@dataclass(frozen=True)
class CareMaintenanceAction:
    action: str
    target_public_ids: Tuple[str, ...]
    proposed_text: Optional[str] = None
    reason: str = ''


@dataclass(frozen=True)
class CareMaintenanceProposal:
    stream_id: int
    actions: Tuple[CareMaintenanceAction, ...] = ()


@dataclass(frozen=True)
class CareMaintenanceApplyResult:
    applied: bool
    reason: str


class CareMaintenanceReader(Protocol):
    async def propose(self, request: CareMaintenanceRequest) -> object:
        ...


class CareMaintenanceService:
    """Builds bounded cleanup proposals without applying them."""

    def __init__(
        self,
        conversations: ConversationRepository,
        care_marks: CareMarkService,
        reader: CareMaintenanceReader,
    ):
        self.conversations = conversations
        self.care_marks = care_marks
        self.reader = reader

    async def propose_for_stream(
        self, stream_id: int, *, limit: int = MAX_MAINTENANCE_MARKS
    ) -> CareMaintenanceProposal:
        selected_limit = max(1, min(int(limit), MAX_MAINTENANCE_MARKS))
        marks = await self.care_marks.list_for_stream(
            stream_id,
            statuses=('draft', 'active', 'open', 'closed'),
            limit=selected_limit,
        )
        messages = await self.conversations.recent(
            stream_id, MAX_MAINTENANCE_MESSAGES
        )
        request = CareMaintenanceRequest(
            stream_id=stream_id,
            care_marks=tuple(
                CareMaintenanceMark(
                    public_id=mark.public_id,
                    kind=mark.kind,
                    status=mark.status,
                    text=mark.text[:500],
                    has_source=mark.source_message_id is not None,
                )
                for mark in marks
            ),
            recent_messages=tuple(
                CareMaintenanceMessage(
                    role=message.role,
                    content=message.content[:1000],
                )
                for message in messages
            ),
        )
        raw = await self.reader.propose(request)
        return parse_maintenance_proposal(stream_id, raw, marks)

    async def apply_selected(
        self,
        stream_id: int,
        action: CareMaintenanceAction,
    ) -> CareMaintenanceApplyResult:
        if action.action != 'close_attention':
            return CareMaintenanceApplyResult(False, 'unsupported')
        if len(action.target_public_ids) != 1:
            return CareMaintenanceApplyResult(False, 'stale')
        mark = await self.care_marks.get_by_public_id(
            action.target_public_ids[0]
        )
        if (
            mark is None
            or mark.stream_id != stream_id
            or mark.kind != 'attention'
            or mark.status != 'open'
        ):
            return CareMaintenanceApplyResult(False, 'stale')
        updated = await self.care_marks.update(
            mark.public_id, status='closed'
        )
        if updated is None or updated.status != 'closed':
            return CareMaintenanceApplyResult(False, 'stale')
        return CareMaintenanceApplyResult(True, 'closed')

    async def auto_close_after_activity(
        self,
        stream_id: int,
        *,
        protected_public_ids: Sequence[str] = (),
    ) -> Tuple[str, ...]:
        proposal = await self.propose_for_stream(stream_id)
        protected = frozenset(protected_public_ids)
        closed = []
        for action in proposal.actions:
            if len(closed) >= MAX_AUTOMATIC_CLOSES:
                break
            if (
                action.action != 'close_attention'
                or any(
                    public_id in protected
                    for public_id in action.target_public_ids
                )
            ):
                continue
            result = await self.apply_selected(stream_id, action)
            if result.applied:
                closed.extend(action.target_public_ids)
        return tuple(closed)


def parse_maintenance_proposal(
    stream_id: int,
    value: object,
    marks: Sequence[CareMark],
) -> CareMaintenanceProposal:
    if not isinstance(value, dict) or not isinstance(value.get('actions'), list):
        return CareMaintenanceProposal(stream_id)

    by_public = {mark.public_id: mark for mark in marks}
    actions = []
    for raw in value['actions'][:MAX_MAINTENANCE_ACTIONS]:
        action = _parse_action(raw, by_public)
        if action is not None:
            actions.append(action)
    return CareMaintenanceProposal(stream_id, tuple(actions))


def _parse_action(
    value: object, by_public: Dict[str, CareMark]
) -> Optional[CareMaintenanceAction]:
    if not isinstance(value, dict):
        return None
    action = value.get('action')
    raw_targets = value.get('target_public_ids')
    if action not in MAINTENANCE_ACTIONS or not isinstance(raw_targets, list):
        return None
    targets = tuple(dict.fromkeys(
        target
        for target in raw_targets[:5]
        if isinstance(target, str) and target in by_public
    ))
    if not _targets_fit_action(action, targets, by_public):
        return None

    proposed_text = value.get('proposed_text')
    if proposed_text is not None:
        if not isinstance(proposed_text, str):
            return None
        proposed_text = proposed_text.strip()[:500] or None
    if action in {'merge_attention', 'rewrite_mark_text'} and not proposed_text:
        return None
    reason = value.get('reason', '')
    if not isinstance(reason, str):
        reason = ''
    return CareMaintenanceAction(
        action,
        targets,
        proposed_text,
        reason.strip()[:200],
    )


def _targets_fit_action(
    action: str,
    targets: Tuple[str, ...],
    by_public: Dict[str, CareMark],
) -> bool:
    selected = tuple(by_public[target] for target in targets)
    if action == 'merge_attention':
        return len(selected) >= 2 and all(
            mark.kind == 'attention' and mark.status == 'open'
            for mark in selected
        )
    if len(selected) != 1:
        return False
    mark = selected[0]
    if action == 'close_attention':
        return mark.kind == 'attention' and mark.status == 'open'
    if action == 'promote_draft_memory':
        return mark.kind == 'memory' and mark.status == 'draft'
    return True
