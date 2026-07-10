"""Spoken-request gates, pending ask-backs, and Speaker outcome notes.

Everything here is small operation machinery: what counts as an explicit
spoken request, how many state changes one turn may apply, the short-lived
memory of an ask-back waiting for its answer, and the fixed-form notes
that tell the Speaker only what really happened.
"""

from dataclasses import dataclass
import re
import time
import unicodedata
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from yuno.care.models import CareReadResult

if TYPE_CHECKING:
    from yuno.care.service import CareApplication


# Spoken-request gates for state changes. Reader proposals alone are not
# enough for the riskier operations; the current message itself must also
# carry the request, so a stray proposal cannot quietly change state.
_FORGET_REQUEST_TERMS = (
    '忘れて', '忘れよ', '覚えなくていい', '覚えないで', '消して', 'やめて',
    'なかったこと',
)
_REMEMBER_REQUEST_TERMS = (
    '覚えて', '固定', '記憶して', 'メモして', '忘れないで',
)
_CLOSE_REQUEST_TERMS = (
    '閉じて', '閉じよ', 'もう終わ', '解決した', '済んだ', '片付いた',
)
MAX_CLOSE_OPERATIONS = 3
MAX_FORGET_OPERATIONS = 2
MAX_PROMOTE_OPERATIONS = 2

UNCLEAR_OPERATIONS = frozenset({'forget', 'close', 'promote'})

_ASK_BACK_NOTES = {
    'forget': (
        'どれを手放すかは、まだ決めていない。'
        '忘れた、とは言わず、どれのことか短く聞き返していい'
    ),
    'close': (
        'どれを閉じるかは、まだ決めていない。'
        '閉じた、とは言わず、どれのことか短く聞き返していい'
    ),
    'promote': (
        'どれを覚えておくかは、まだ決めていない。'
        '覚えた、とは言わず、どれのことか短く聞き返していい'
    ),
}


PENDING_OPERATION_TTL_SECONDS = 300.0


@dataclass(frozen=True)
class _PendingOperation:
    operation: str
    author_id: str
    expires_at: float


class PendingCareOperations:
    """One short-lived ask-back per stream, waiting for its answer.

    When Yuno asks which mark was meant, the requested operation is kept
    here for a few minutes so the next answer from the same speaker can
    finish it. Nothing is persisted; losing this state only means the
    request has to be said again.
    """

    def __init__(
        self,
        ttl_seconds: float = PENDING_OPERATION_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._pending: Dict[int, _PendingOperation] = {}

    def set(self, stream_id: int, author_id: str, operation: str) -> None:
        if operation not in UNCLEAR_OPERATIONS:
            return
        self._pending[stream_id] = _PendingOperation(
            operation=operation,
            author_id=str(author_id),
            expires_at=self._clock() + self._ttl_seconds,
        )

    def peek(self, stream_id: int, author_id: str) -> Optional[str]:
        """The waiting operation for this speaker, or None.

        A different speaker's turn leaves the pending ask-back in place;
        only expiry or an explicit clear removes it.
        """
        pending = self._pending.get(stream_id)
        if pending is None:
            return None
        if self._clock() >= pending.expires_at:
            del self._pending[stream_id]
            return None
        if pending.author_id != str(author_id):
            return None
        return pending.operation

    def clear(self, stream_id: int) -> None:
        self._pending.pop(stream_id, None)


def normalize_for_match(value: str) -> str:
    normalized = unicodedata.normalize('NFKC', value).casefold()
    return re.sub(r'[\W_]+', '', normalized, flags=re.UNICODE)


def requests_forget(content: str) -> bool:
    return _contains_any(content, _FORGET_REQUEST_TERMS)


def requests_remember(content: str) -> bool:
    return _contains_any(content, _REMEMBER_REQUEST_TERMS)


def requests_close(content: str) -> bool:
    return _contains_any(content, _CLOSE_REQUEST_TERMS)


def care_operations_log_line(
    *,
    route_reason: str,
    spoke: bool,
    source_content: str,
    result: CareReadResult,
    application: 'CareApplication',
    pending_operation: str = '',
) -> str:
    """One observation line: counts and enums only, never message text.

    The message content is reduced to which gate lexicons it hit; the
    hit is a known-vocabulary match, not the speaker's actual intent.
    A missing hit alone is not a vocabulary gap: close has no spoken
    gate, and pending ask-backs complete forget/promote without one.
    Gap candidates are forget/promote lines with pending=none, proposals
    present, and a gate block.
    """
    hits = [
        name
        for name, hit in (
            ('forget', requests_forget(source_content)),
            ('remember', requests_remember(source_content)),
            ('close', requests_close(source_content)),
        )
        if hit
    ]
    proposed = (
        f'close:{len(result.close_care_mark_ids)}'
        f',forget:{len(result.forget_care_mark_ids)}'
        f',promote:{len(result.promote_care_mark_ids)}'
    )
    applied = (
        f'created:{len(application.created_care_mark_ids)}'
        f',touched:{len(application.touched_care_mark_ids)}'
        f',closed:{len(application.closed_care_mark_ids)}'
        f',forgotten:{len(application.forgotten_care_mark_ids)}'
        f',promoted:{len(application.promoted_care_mark_ids)}'
    )
    blocked = ','.join(
        f'{operation}:{reason}:{count}'
        for operation, reason, count in application.blocked_operations
    ) or 'none'
    return (
        f'route={route_reason or "none"}'
        f' spoke={"true" if spoke else "false"}'
        f' lexical_request_hit={",".join(hits) or "none"}'
        f' proposed={proposed}'
        f' applied={applied}'
        f' blocked={blocked}'
        f' unclear={result.unclear_operation or "none"}'
        f' pending={pending_operation or "none"}'
        f' pending_outcome={_pending_outcome(result, application, pending_operation)}'
    )


def _pending_outcome(
    result: CareReadResult,
    application: 'CareApplication',
    pending_operation: str,
) -> str:
    if not pending_operation:
        return 'none'
    fulfilled = {
        'close': application.closed_care_mark_ids,
        'forget': application.forgotten_care_mark_ids,
        'promote': application.promoted_care_mark_ids,
    }.get(pending_operation)
    if fulfilled:
        return 'applied'
    if result.unclear_operation:
        return 're_asked'
    # Nothing happened; whether the answer was unrelated is not decided
    # here, only that no state changed.
    return 'no_action'


def care_outcome_note(
    source_content: str,
    application: 'CareApplication',
    unclear_operation: str = '',
) -> str:
    """Short fixed-form Speaker notes about what actually happened.

    Lines exist only for state that really changed, plus an ask-back line
    when a request could not be tied to one mark, and explicit
    "do not claim it" lines when the message asked for a change that did
    not happen. Forgotten mark text is never repeated here.
    """
    forgot = bool(application.forgotten_care_mark_ids)
    closed = bool(application.closed_care_mark_ids)
    promoted = bool(application.promoted_care_mark_ids)

    parts: List[str] = []
    if forgot:
        parts.append('いま、頼まれたことをひとつ手放して、もう覚えていないことにした')
    if closed:
        parts.append('いま、あとで見るつもりだったことをひと区切りつけて閉じた')
    if promoted:
        parts.append('いま、言われたことをちゃんと覚えることにした')

    fulfilled = {'forget': forgot, 'close': closed, 'promote': promoted}
    unclear = (
        unclear_operation
        if unclear_operation in UNCLEAR_OPERATIONS
        and not fulfilled[unclear_operation]
        else ''
    )
    if unclear:
        parts.append(_ASK_BACK_NOTES[unclear])

    if (
        requests_remember(source_content)
        and not promoted
        and unclear != 'promote'
    ):
        parts.append(_remember_outcome(application))
    if requests_forget(source_content) and not forgot and unclear != 'forget':
        parts.append('忘れることは、いまここでは起きていない。忘れた、とは言わない')
    if requests_close(source_content) and not closed and unclear != 'close':
        parts.append('閉じることは、いまここでは起きていない。閉じた、とは言わない')
    return '\n'.join(parts)


def _remember_outcome(application: 'CareApplication') -> str:
    by_id = {mark.public_id: mark for mark in application.affected_care_marks}
    created = [
        by_id[public_id]
        for public_id in application.created_care_mark_ids
        if public_id in by_id
    ]
    touched = [
        by_id[public_id]
        for public_id in application.touched_care_mark_ids
        if public_id in by_id
    ]
    if any(mark.kind == 'memory' and mark.status == 'active' for mark in created):
        return 'いま、言われたことを覚えることにした'
    if any(mark.kind == 'memory' and mark.status == 'draft' for mark in created):
        return 'いま、言われたことはそっと預かっている。覚えた、とまでは言い切らない'
    if any(mark.kind == 'memory' and mark.status == 'active' for mark in touched):
        return 'それは前から覚えている'
    return '覚えることは、いまここでは起きていない。覚えた、とは言わない'


def _contains_any(content: str, terms: Tuple[str, ...]) -> bool:
    normalized = normalize_for_match(content)
    if not normalized:
        return False
    return any(normalize_for_match(term) in normalized for term in terms)
