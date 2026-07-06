from dataclasses import dataclass
import re
import unicodedata
from typing import Dict, Tuple

from yuno.care_marks.models import CareMark
from yuno.care_marks.service import CareMarkService
from yuno.conversation.context import REFERENCE_LIMIT
from yuno.read_cues.service import ReadCueService


@dataclass(frozen=True)
class ReferenceSelection:
    care_mark_ids: Tuple[str, ...] = ()


class ReferenceSelector:
    '''Select a few visible CareMarks; it never decides whether to reply.'''

    def __init__(
        self,
        care_marks: CareMarkService,
        read_cues: ReadCueService,
    ):
        self.care_marks = care_marks
        self.read_cues = read_cues

    async def select(
        self, stream_id: int, current_message: str
    ) -> ReferenceSelection:
        candidates = await self.care_marks.list_for_stream(
            stream_id,
            statuses=('active', 'open'),
            limit=20,
        )
        marks = [
            mark for mark in candidates
            if (
                mark.kind == 'memory' and mark.status == 'active'
                or mark.kind == 'attention' and mark.status == 'open'
            )
        ]
        if not marks:
            return ReferenceSelection()
        by_id: Dict[int, CareMark] = {mark.id: mark for mark in marks}
        scores: Dict[int, float] = {}
        compact_message = _compact(current_message)

        for cue in await self.read_cues.list_for_stream(
            stream_id, statuses=('active',), limit=40
        ):
            normalized_cue = _compact(cue.term)
            if (
                cue.care_mark_id in by_id
                and normalized_cue
                and normalized_cue in compact_message
            ):
                scores[cue.care_mark_id] = (
                    scores.get(cue.care_mark_id, 0.0)
                    + 3.0
                    + cue.weight
                )

        message_parts = _parts(current_message)
        for mark in marks:
            overlap = len(message_parts & _parts(mark.text))
            if overlap >= 3:
                scores[mark.id] = scores.get(mark.id, 0.0) + float(overlap)

        ranked = sorted(
            (
                (score, by_id[mark_id].public_id)
                for mark_id, score in scores.items()
            ),
            key=lambda item: (-item[0], item[1]),
        )
        return ReferenceSelection(tuple(
            public_id for _, public_id in ranked[:REFERENCE_LIMIT]
        ))


def _parts(value: str) -> set:
    compact = _compact(value)
    parts = set()
    for size in (2, 3):
        parts.update(
            compact[index:index + size]
            for index in range(max(0, len(compact) - size + 1))
        )
    return parts


def _compact(value: str) -> str:
    normalized = unicodedata.normalize('NFKC', value).casefold()
    return re.sub(r'[\W_]+', '', normalized, flags=re.UNICODE)
