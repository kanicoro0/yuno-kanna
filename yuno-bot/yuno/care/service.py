from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from yuno.care.models import CareReadRequest, CareReadResult
from yuno.care.operations import (
    MAX_CLOSE_OPERATIONS,
    MAX_FORGET_OPERATIONS,
    MAX_PROMOTE_OPERATIONS,
    normalize_for_match,
    requests_forget,
    requests_remember,
)
from yuno.care.safety import looks_sensitive
from yuno.care_marks.models import CareMark
from yuno.care_marks.service import CareMarkService
from yuno.conversation.context import build_speaker_history
from yuno.conversation.repository import ConversationRepository
from yuno.read_cues.models import ReadCue
from yuno.read_cues.service import ReadCueService


@dataclass(frozen=True)
class CareState:
    care_marks: Tuple[CareMark, ...] = ()
    read_cues: Tuple[ReadCue, ...] = ()


@dataclass(frozen=True)
class CareApplication:
    created_care_mark_ids: Tuple[str, ...] = ()
    touched_care_mark_ids: Tuple[str, ...] = ()
    upserted_read_cue_ids: Tuple[int, ...] = ()
    include_care_mark_ids: Tuple[str, ...] = ()
    affected_care_marks: Tuple[CareMark, ...] = ()
    closed_care_mark_ids: Tuple[str, ...] = ()
    forgotten_care_mark_ids: Tuple[str, ...] = ()
    promoted_care_mark_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CareTriggerDecision:
    run: bool
    reason: str
    cue_salience: float = 0.0


_CARE_TRIGGER_TERMS = (
    ('explicit_memory', ('覚えて', '忘れないで', 'メモ', '記憶')),
    ('attention_language', ('あとで', '後で見る')),
    ('name_preference', ('呼んで', '呼び名', '名前')),
    ('preference', ('好き', '嫌い', '苦手', '好み')),
    ('schedule_or_task', ('予定', '締切', 'やること', '忘れそう')),
    ('memory_operation', (
        '忘れて', '覚えなくていい', '閉じていい', '固定して', 'なかったこと',
    )),
)
_STRONG_CUE_SALIENCE = 0.5
_STRONG_ATTENTION_OVERLAP = 0.6


class CareService:
    def __init__(
        self,
        conversations: ConversationRepository,
        care_marks: CareMarkService,
        read_cues: ReadCueService,
    ):
        self.conversations = conversations
        self.care_marks = care_marks
        self.read_cues = read_cues

    async def current_state(self, stream_id: int) -> CareState:
        marks = await self.care_marks.list_for_stream(
            stream_id,
            statuses=('draft', 'active', 'open', 'closed'),
            limit=20,
        )
        cues = await self.read_cues.list_for_stream(
            stream_id, statuses=('active',), limit=40
        )
        visible_mark_ids = {mark.id for mark in marks}
        visible_cues = tuple(
            cue for cue in cues if cue.care_mark_id in visible_mark_ids
        )
        return CareState(tuple(marks), visible_cues)

    async def build_request(
        self,
        stream_id: int,
        current_message: str,
        addressing_strength: float,
        cue_salience_value: float,
        state: CareState,
        route_reason: str = '',
        reply_mode: str = 'none',
    ) -> CareReadRequest:
        recent = await self.conversations.recent(stream_id, 8)
        public_ids = {mark.id: mark.public_id for mark in state.care_marks}
        return CareReadRequest(
            current_message=current_message[:2000],
            recent_messages=tuple(build_speaker_history(recent, 6000)),
            care_marks=tuple({
                'public_id': mark.public_id,
                'kind': mark.kind,
                'status': mark.status,
                'text': mark.text,
            } for mark in state.care_marks),
            read_cues=tuple({
                'care_mark_public_id': public_ids.get(cue.care_mark_id),
                'term': cue.term,
                'weight': cue.weight,
                'status': cue.status,
            } for cue in state.read_cues if cue.care_mark_id in public_ids),
            addressing_strength=max(0.0, min(1.0, addressing_strength)),
            cue_salience=max(0.0, min(0.7, cue_salience_value)),
            route_reason=route_reason,
            reply_mode=reply_mode,
        )

    async def apply(
        self,
        stream_id: int,
        source_message_id: int,
        result: CareReadResult,
        source_content: str = '',
    ) -> CareApplication:
        state = await self.current_state(stream_id)
        by_public: Dict[str, CareMark] = {
            mark.public_id: mark for mark in state.care_marks
        }
        # Duplicate checks read every mark of the candidate's kind, hidden
        # included, so they are not limited by the visible-state window.
        dedup_marks: Dict[str, List[CareMark]] = {}
        candidate_targets: Dict[str, Optional[CareMark]] = {}
        created = []
        touched = []
        affected: List[CareMark] = []

        for public_id in result.touch_care_mark_ids:
            mark = by_public.get(public_id)
            if mark is None or public_id in touched:
                continue
            touched_mark = await self.care_marks.touch(public_id)
            if touched_mark:
                touched.append(public_id)
                _remember_affected(affected, touched_mark)

        for candidate in result.care_mark_candidates[:5]:
            if not _valid_candidate_status(candidate.kind, candidate.status):
                continue
            status = candidate.status
            if candidate.kind == 'memory' and status == 'active' and (
                candidate.sensitive
                or candidate.about_other_person
                or looks_sensitive(candidate.text)
            ):
                status = 'draft'
            normalized = normalize_for_match(candidate.text)
            if not normalized:
                continue
            if candidate.kind not in dedup_marks:
                dedup_marks[candidate.kind] = (
                    await self.care_marks.list_all_for_kind(
                        stream_id, candidate.kind
                    )
                )
            same_text = [
                mark for mark in dedup_marks[candidate.kind]
                if normalize_for_match(mark.text) == normalized
            ]
            matching = next((
                mark for mark in same_text
                if mark.status != 'hidden'
                and (
                    candidate.kind == 'memory'
                    or mark.status == 'open' and status == 'open'
                )
            ), None)
            if matching is not None:
                if matching.public_id not in touched:
                    touched_mark = await self.care_marks.touch(
                        matching.public_id
                    )
                    if touched_mark:
                        touched.append(matching.public_id)
                        _remember_affected(affected, touched_mark)
                _remember_target(candidate_targets, normalized, matching)
                continue
            if any(mark.status == 'hidden' for mark in same_text):
                # The same text was hidden on purpose; a candidate must not
                # quietly bring it back as a new mark.
                continue
            try:
                mark = await self.care_marks.create(
                    stream_id=stream_id,
                    kind=candidate.kind,
                    status=status,
                    text=candidate.text,
                    source_message_id=source_message_id,
                )
            except ValueError:
                continue
            dedup_marks[candidate.kind].append(mark)
            by_public[mark.public_id] = mark
            created.append(mark.public_id)
            _remember_affected(affected, mark)
            _remember_target(candidate_targets, normalized, mark)

        closed = await self._apply_close(result, by_public, affected)
        forgotten = await self._apply_forget(
            result, source_content, created, by_public, affected
        )
        promoted = await self._apply_promote(
            result, source_content, by_public, affected
        )

        cue_ids = []
        for update in result.read_cue_updates[:8]:
            mark = by_public.get(update.care_mark_public_id or '')
            if mark is None and update.candidate_text:
                mark = candidate_targets.get(
                    normalize_for_match(update.candidate_text)
                )
            if mark is None:
                continue
            try:
                cue = await self.read_cues.upsert(
                    mark.id, update.term, update.weight
                )
            except ValueError:
                continue
            if cue.id not in cue_ids:
                cue_ids.append(cue.id)

        included = tuple(
            public_id
            for public_id in dict.fromkeys(result.include_care_mark_ids)
            if public_id in by_public
            and (
                by_public[public_id].kind == 'memory'
                and by_public[public_id].status == 'active'
                or by_public[public_id].kind == 'attention'
                and by_public[public_id].status == 'open'
            )
        )
        return CareApplication(
            tuple(created), tuple(touched), tuple(cue_ids), included,
            tuple(affected),
            closed_care_mark_ids=tuple(closed),
            forgotten_care_mark_ids=tuple(forgotten),
            promoted_care_mark_ids=tuple(promoted),
        )

    async def _apply_close(
        self,
        result: CareReadResult,
        by_public: Dict[str, CareMark],
        affected: List[CareMark],
    ) -> List[str]:
        closed: List[str] = []
        for public_id in result.close_care_mark_ids:
            if len(closed) >= MAX_CLOSE_OPERATIONS:
                break
            mark = by_public.get(public_id)
            if mark is None or mark.kind != 'attention' or mark.status != 'open':
                continue
            updated = await self.care_marks.update(public_id, status='closed')
            if updated is not None:
                closed.append(public_id)
                by_public[public_id] = updated
                _remember_affected(affected, updated)
        return closed

    async def _apply_forget(
        self,
        result: CareReadResult,
        source_content: str,
        created: List[str],
        by_public: Dict[str, CareMark],
        affected: List[CareMark],
    ) -> List[str]:
        if not result.forget_care_mark_ids:
            return []
        if not requests_forget(source_content):
            return []
        forgotten: List[str] = []
        for public_id in result.forget_care_mark_ids:
            if len(forgotten) >= MAX_FORGET_OPERATIONS:
                break
            mark = by_public.get(public_id)
            if (
                mark is None
                or mark.status == 'hidden'
                or public_id in created
            ):
                continue
            updated = await self.care_marks.update(public_id, status='hidden')
            if updated is not None:
                forgotten.append(public_id)
                by_public[public_id] = updated
                _remember_affected(affected, updated)
        return forgotten

    async def _apply_promote(
        self,
        result: CareReadResult,
        source_content: str,
        by_public: Dict[str, CareMark],
        affected: List[CareMark],
    ) -> List[str]:
        if not result.promote_care_mark_ids:
            return []
        if not requests_remember(source_content):
            return []
        promoted: List[str] = []
        for public_id in result.promote_care_mark_ids:
            if len(promoted) >= MAX_PROMOTE_OPERATIONS:
                break
            mark = by_public.get(public_id)
            if (
                mark is None
                or mark.kind != 'memory'
                or mark.status != 'draft'
                or looks_sensitive(mark.text)
            ):
                continue
            updated = await self.care_marks.update(public_id, status='active')
            if updated is not None:
                promoted.append(public_id)
                by_public[public_id] = updated
                _remember_affected(affected, updated)
        return promoted


def cue_salience(content: str, cues: Iterable[ReadCue]) -> float:
    normalized = normalize_for_match(content)
    if not normalized:
        return 0.0
    matched = [
        cue.weight
        for cue in cues
        if normalize_for_match(cue.term)
        and normalize_for_match(cue.term) in normalized
    ]
    return min(0.7, max(matched, default=0.0))


def immediate_care_decision(
    content: str, state: CareState
) -> CareTriggerDecision:
    normalized = normalize_for_match(content)
    for reason, terms in _CARE_TRIGGER_TERMS:
        if any(normalize_for_match(term) in normalized for term in terms):
            return CareTriggerDecision(True, reason)

    salience = cue_salience(content, state.read_cues)
    if salience >= _STRONG_CUE_SALIENCE:
        return CareTriggerDecision(True, 'strong_cue', salience)
    if attention_overlap(content, state.care_marks) >= _STRONG_ATTENTION_OVERLAP:
        return CareTriggerDecision(True, 'open_attention', salience)
    return CareTriggerDecision(False, 'low_signal', salience)


def overlaps_attention(content: str, marks: Iterable[CareMark]) -> bool:
    return attention_overlap(content, marks) >= _STRONG_ATTENTION_OVERLAP


def attention_overlap(content: str, marks: Iterable[CareMark]) -> float:
    message_grams = _grams(content)
    if not message_grams:
        return 0.0
    scores = (
        len(message_grams & mark_grams) / len(mark_grams)
        for mark in marks
        if mark.kind == 'attention' and mark.status == 'open'
        for mark_grams in (_grams(mark.text),)
        if mark_grams
    )
    return max(scores, default=0.0)


def _valid_candidate_status(kind: str, status: str) -> bool:
    return (
        kind == 'memory' and status in {'draft', 'active'}
    ) or (
        kind == 'attention' and status in {'open', 'closed'}
    )


def _remember_target(
    targets: Dict[str, Optional[CareMark]],
    normalized_text: str,
    mark: CareMark,
) -> None:
    if normalized_text not in targets:
        targets[normalized_text] = mark
    elif targets[normalized_text] != mark:
        targets[normalized_text] = None


def _remember_affected(marks: List[CareMark], mark: CareMark) -> None:
    for index, existing in enumerate(marks):
        if existing.public_id == mark.public_id:
            marks[index] = mark
            return
    marks.append(mark)


def _grams(value: str) -> set:
    compact = normalize_for_match(value)
    return {
        compact[index:index + 3]
        for index in range(max(0, len(compact) - 2))
    }
