import json
import math
from typing import Any, Dict, Iterable, Tuple

from yuno.care.models import (
    CareMarkCandidate,
    CareReadRequest,
    CareReadResult,
    ReadCueUpdate,
)
from yuno.care.safety import looks_sensitive
from yuno.infra.openai_client import OpenAITextClient


CARE_SYSTEM_PROMPT = '''あなたは唯乃（ゆの）のCareReaderです。返答本文や口調指示は書きません。
同じ場のテキスト会話だけを読み、失くしたくない印、まだ閉じないもの、印へ戻るための弱い語をJSONで返します。
言われていないこと、心理の断定、幻や連想を事実にしません。迷うmemory候補はdraftにします。
他人についての伝聞、医療、恋愛、家庭などセンシティブなmemory候補はactiveにしません。
ReadCueは独立した記憶ではなくCareMarkへ戻るための索引です。ReadCueそのものを返答材料にしません。
利用できる入力はテキストだけです。画像、写真、添付、音声、外部リンク本文、周囲の様子を読んだ前提で候補を作りません。
未実装機能が使えることを前提に候補を作りません。
listening通常発言へ割り込むのは、今この場で本当に一言返したい時だけshould_speak=trueにします。
JSON fields: wants_to_speak, should_speak,
care_mark_candidates[{kind,status,text,confidence,sensitive,about_other_person}],
read_cue_updates[{care_mark_public_id,candidate_text,term,weight}],
touch_care_mark_ids, include_care_mark_ids。
kindはmemoryまたはattention。memory statusはdraftまたはactive、attention statusはopenまたはclosedです。'''


class CareReader:
    def __init__(self, client: OpenAITextClient):
        self.client = client

    async def read(self, request: CareReadRequest) -> CareReadResult:
        raw = await self.client.complete_json([
            {'role': 'system', 'content': CARE_SYSTEM_PROMPT},
            {
                'role': 'user',
                'content': json.dumps(request.to_dict(), ensure_ascii=False),
            },
        ])
        return parse_care_result(raw)


def parse_care_result(data: Any) -> CareReadResult:
    if not isinstance(data, dict):
        return CareReadResult()
    candidates = []
    for raw in _objects(data.get('care_mark_candidates'), 5):
        kind = str(raw.get('kind', ''))
        status = str(raw.get('status', ''))
        text = str(raw.get('text', '')).strip()[:500]
        if not text or not _valid_candidate_status(kind, status):
            continue
        sensitive = _flag(raw.get('sensitive')) or looks_sensitive(text)
        about_other_person = _flag(raw.get('about_other_person'))
        if kind == 'memory' and status == 'active' and (
            sensitive or about_other_person
        ):
            status = 'draft'
        candidates.append(CareMarkCandidate(
            kind=kind,
            status=status,
            text=text,
            confidence=_number(raw.get('confidence'), 0.5),
            sensitive=sensitive,
            about_other_person=about_other_person,
        ))

    cue_updates = []
    for raw in _objects(data.get('read_cue_updates'), 8):
        term = str(raw.get('term', '')).strip()[:80]
        public_id = _optional_id(raw.get('care_mark_public_id'))
        candidate_text = str(raw.get('candidate_text', '')).strip()[:500] or None
        if term and (public_id or candidate_text):
            cue_updates.append(ReadCueUpdate(
                term=term,
                weight=_number(raw.get('weight'), 0.3),
                care_mark_public_id=public_id,
                candidate_text=candidate_text,
            ))

    return CareReadResult(
        wants_to_speak=_flag(data.get('wants_to_speak')),
        should_speak=_flag(data.get('should_speak')),
        care_mark_candidates=tuple(candidates),
        read_cue_updates=tuple(cue_updates),
        touch_care_mark_ids=_ids(data.get('touch_care_mark_ids'), 8),
        include_care_mark_ids=_ids(data.get('include_care_mark_ids'), 8),
    )


def _valid_candidate_status(kind: str, status: str) -> bool:
    return (
        kind == 'memory' and status in {'draft', 'active'}
    ) or (
        kind == 'attention' and status in {'open', 'closed'}
    )


def _objects(value: Any, limit: int) -> Iterable[Dict[str, Any]]:
    if not isinstance(value, list):
        return ()
    return (item for item in value[:limit] if isinstance(item, dict))


def _optional_id(value: Any) -> str:
    text = str(value).strip()[:40]
    return text if text.startswith('care_') else ''


def _ids(value: Any, limit: int) -> Tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result = []
    for item in value:
        public_id = _optional_id(item)
        if public_id and public_id not in result:
            result.append(public_id)
    return tuple(result[:limit])


def _number(value: Any, default: float) -> float:
    try:
        number = float(value)
        return max(0.0, min(1.0, number)) if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _flag(value: Any) -> bool:
    return value is True
