import json
import math
from typing import Any, Dict, Iterable, Tuple

from yuno.care.models import (
    AttentionCandidate, CareReadRequest, CareReadResult,
    InterestUpdate, MemoryCandidate,
)
from yuno.infra.openai_client import OpenAITextClient


CARE_SYSTEM_PROMPT = """あなたは唯乃（ゆの）のCareReaderです。返答本文や口調指示は書きません。
同じ場の会話だけを読み、失くしたくない印、まだ閉じないもの、少し気になる語、参照候補をJSONで返します。
言われていないこと、心理の断定、幻や連想を事実にしません。迷うMemoryMarkはpendingにします。
他人についての伝聞、医療、恋愛、家庭などセンシティブな候補はactiveにせずpendingにします。
listening通常発言へ割り込むのは、今この場で本当に一言返したい時だけshould_speak=trueにします。
JSON fields: wants_to_speak, should_speak,
memory_candidates[{content,kind,status,confidence,sensitive,about_other_person}],
attention_candidates[{text,rank}], touch_attention_ids,
interest_updates[{term,weight}], include_memory_ids, include_attention_ids。"""


class CareReader:
    def __init__(self, client: OpenAITextClient):
        self.client = client

    async def read(self, request: CareReadRequest) -> CareReadResult:
        raw = await self.client.complete_json([
            {"role": "system", "content": CARE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(request.to_dict(), ensure_ascii=False)},
        ])
        return parse_care_result(raw)


def parse_care_result(data: Any) -> CareReadResult:
    if not isinstance(data, dict):
        return CareReadResult()
    memories = []
    for raw in _objects(data.get("memory_candidates"), 3):
        kind = str(raw.get("kind", ""))
        status = str(raw.get("status", "pending"))
        content = str(raw.get("content", "")).strip()[:500]
        if kind not in {"pin", "correction"} or status not in {"pending", "active"} or not content:
            continue
        if status == "active" and (
            _flag(raw.get("sensitive"))
            or _flag(raw.get("about_other_person"))
            or _looks_sensitive(content)
        ):
            status = "pending"
        memories.append(MemoryCandidate(
            content, kind, status, _number(raw.get("confidence"), 0.5)
        ))
    attentions = []
    for raw in _objects(data.get("attention_candidates"), 3):
        text = str(raw.get("text", "")).strip()[:400]
        if text:
            attentions.append(AttentionCandidate(text, _number(raw.get("rank"), 0.5)))
    interests = []
    for raw in _objects(data.get("interest_updates"), 5):
        term = str(raw.get("term", "")).strip()[:80]
        if term:
            interests.append(InterestUpdate(term, _number(raw.get("weight"), 0.3)))
    return CareReadResult(
        wants_to_speak=_flag(data.get("wants_to_speak")),
        should_speak=_flag(data.get("should_speak")),
        memory_candidates=tuple(memories),
        attention_candidates=tuple(attentions),
        touch_attention_ids=_ids(data.get("touch_attention_ids"), "att_", 8),
        interest_updates=tuple(interests),
        include_memory_ids=_ids(data.get("include_memory_ids"), "mem_", 8),
        include_attention_ids=_ids(data.get("include_attention_ids"), "att_", 8),
    )


def _objects(value: Any, limit: int) -> Iterable[Dict[str, Any]]:
    if not isinstance(value, list):
        return ()
    return (item for item in value[:limit] if isinstance(item, dict))


def _ids(value: Any, prefix: str, limit: int) -> Tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result = []
    for item in value:
        text = str(item).strip()[:40]
        if text.startswith(prefix) and text not in result:
            result.append(text)
    return tuple(result[:limit])


def _number(value: Any, default: float) -> float:
    try:
        number = float(value)
        return max(0.0, min(1.0, number)) if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _flag(value: Any) -> bool:
    return value is True


def _looks_sensitive(content: str) -> bool:
    markers = (
        "病気", "医療", "診断", "治療", "薬", "通院", "恋愛", "好きな人",
        "彼氏", "彼女", "家族", "家庭", "両親", "父親", "母親",
    )
    return any(marker in content for marker in markers)
