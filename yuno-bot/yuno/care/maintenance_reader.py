import json
from typing import Dict

from yuno.care.maintenance import (
    CareMaintenanceRequest,
    MAX_MAINTENANCE_MARKS,
    MAX_MAINTENANCE_MESSAGES,
)
from yuno.infra.openai_client import OpenAITextClient


CARE_MAINTENANCE_SYSTEM_PROMPT = '''あなたは唯乃（ゆの）のCareMark整理案を作るreaderです。
返答文や新しい記憶は作らず、渡されたmarkをどう保つかの提案だけをJSONで返します。

安定したmemoryは、明確に誤っている場合を除いてkeepにします。
attentionを閉じるのは、軽い用件が会話上はっきり解決済みの時だけです。
merge_attentionは、同じ未完了事項を指すopen attention同士に限ります。
rewrite_mark_textは、内容を変えず、明らかに冗長・重複した文を短くする時だけです。
判断が曖昧ならkeepにするか、actionを出しません。
事実を推測・創作しません。最近の無関係な会話をmemoryへ要約しません。
新しいmarkを作りません。入力にないpublic_idを使いません。

JSON shape:
{"actions":[{"action":"keep|close_attention|merge_attention|rewrite_mark_text|promote_draft_memory|hide_or_ignore_noisy_mark","target_public_ids":["care_..."],"proposed_text":null,"reason":"短い理由"}]}
actionsがなければ{"actions":[]}を返します。'''


class LLMCareMaintenanceReader:
    """Makes one structured LLM call for one bounded maintenance request."""

    def __init__(self, client: OpenAITextClient):
        self.client = client

    async def propose(self, request: CareMaintenanceRequest) -> object:
        raw = await self.client.complete_json([
            {'role': 'system', 'content': CARE_MAINTENANCE_SYSTEM_PROMPT},
            {
                'role': 'user',
                'content': json.dumps(
                    _request_payload(request), ensure_ascii=False
                ),
            },
        ])
        return raw if isinstance(raw, dict) else {}


def _request_payload(request: CareMaintenanceRequest) -> Dict[str, object]:
    return {
        'care_marks': [
            {
                'public_id': mark.public_id,
                'kind': mark.kind,
                'status': mark.status,
                'text': mark.text[:500],
                'has_source': mark.has_source,
            }
            for mark in request.care_marks[:MAX_MAINTENANCE_MARKS]
        ],
        'recent_messages': [
            {
                'role': message.role,
                'content': message.content[:1000],
            }
            for message in request.recent_messages[:MAX_MAINTENANCE_MESSAGES]
        ],
    }
