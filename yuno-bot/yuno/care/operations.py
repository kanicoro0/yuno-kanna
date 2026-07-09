"""Spoken-request gates and Speaker-facing outcome notes for care marks.

Everything here is pure text logic: what counts as an explicit spoken
request, how many state changes one turn may apply, and the short
fixed-form notes that tell the Speaker only what really happened.
"""

import re
import unicodedata
from typing import TYPE_CHECKING, List, Tuple

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


def normalize_for_match(value: str) -> str:
    normalized = unicodedata.normalize('NFKC', value).casefold()
    return re.sub(r'[\W_]+', '', normalized, flags=re.UNICODE)


def requests_forget(content: str) -> bool:
    return _contains_any(content, _FORGET_REQUEST_TERMS)


def requests_remember(content: str) -> bool:
    return _contains_any(content, _REMEMBER_REQUEST_TERMS)


def requests_close(content: str) -> bool:
    return _contains_any(content, _CLOSE_REQUEST_TERMS)


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
