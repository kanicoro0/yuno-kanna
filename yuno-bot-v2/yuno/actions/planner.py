import json
from typing import Any, Dict, List

from yuno.actions.schema import ActionPlan
from yuno.infra.openai_client import OpenAIJsonClient


PLANNER_SYSTEM_PROMPT = """あなたはDiscord bot『ゆの』のPlannerです。返答本文は書かず、どこを見るかと行動候補をJSONで示します。
Plannerは切るためではなく、見る場所を決めます。内部の注意はhigh/medium/lowで柔らかく、候補だけを出してください。
candidate_actions.typeはspeak/record/react/noopのみです。recordはrecord_action(add/rewrite/delete), scope, target_id, dataを使います。
記憶操作はまだ実行されず、Executorが検証します。入力に明確な記憶依頼がない場合、recordを推測で作らないでください。
tagsは2〜4個を目安に、preference/fact/behavior/policy/project/note/correction/tone/reply_style/reply_length/
confirmation/nonmention/server_behavior/channel_behavior/dm_behavior/memory_design/action_plan/retrieval/planner/speaker/
executor/commit/discord_bot/yuno_v2/writing/art/philosophy/app_design/codeを優先してください。
JSON fields: reading{main_point,subtext,do_not_flatten}, attention{topics,scopes},
memory_hints[{id,relevance,use,reason}], candidate_actions[], speaker_guidance{depth,style,avoid}。"""


class Planner:
    def __init__(self, client: OpenAIJsonClient):
        self.client = client

    async def plan(
        self,
        content: str,
        context: str,
        scopes: List[str],
        recent_history: List[Dict[str, str]],
        memory_candidates: List[Dict[str, Any]],
    ) -> ActionPlan:
        payload = {
            "message": content,
            "context": context,
            "available_scopes": scopes,
            "recent_history": recent_history[-12:],
            "pre_retrieval_candidates": memory_candidates,
        }

        def fallback() -> Dict[str, Any]:
            return {
                "reading": {"main_point": content[:300], "subtext": "mock planner", "do_not_flatten": []},
                "attention": {"topics": {"current_message": "high"}, "scopes": {"user": "high"}},
                "memory_hints": [
                    {"id": item["id"], "relevance": "medium", "use": "possible", "reason": item["retrieval_reason"]}
                    for item in memory_candidates[:3]
                ],
                "candidate_actions": [{"type": "speak", "confidence": "high", "brief": "ユーザーの発言へ自然に応答する"}],
                "speaker_guidance": {"depth": "short", "style": "natural", "avoid": ["未実装機能を実装済みと装う"]},
            }

        raw = await self.client.complete_json([
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ], fallback)
        return ActionPlan.from_dict(raw)
