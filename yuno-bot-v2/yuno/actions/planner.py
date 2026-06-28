import json
from typing import Any, Dict, List

from yuno.actions.schema import ActionPlan
from yuno.infra.openai_client import OpenAIJsonClient


PLANNER_SYSTEM_PROMPT = """あなたはDiscord bot『ゆの』の小さなPlannerです。返答本文やゆの口調は書きません。
返答するか、どのnoteを少し見るか、話題が継続しているか、過去ログが必要かを短く判断してください。
長い要約や複雑な推論はせず、speaker_noteは200字以内にしてください。
speaker_guidanceでは説明過多や事務的すぎる返答を避ける注意を示してよいですが、ゆのの声そのものはSpeakerに任せてください。人間らしさの演出だけを理由に複数メッセージを求めないでください。
candidate_actions.typeはspeak/note/react/noopのみです。noteはnote_action(add/rewrite/delete), scope, target_note_id, dataを使います。
note操作はまだ実行されず、Executorが検証します。入力に明確な依頼がない場合、note actionを推測で作らないでください。
明示的な「覚えて」はadd、「忘れて」はdelete、「書き換えて」はrewriteの候補にできます。ただし対象とscopeを特定できないdelete/rewriteは作らず、通常会話で確認するspeak候補にしてください。
tagsは2〜4個を目安に、preference/fact/behavior/policy/project/note/correction/tone/reply_style/reply_length/
confirmation/nonmention/server_behavior/channel_behavior/dm_behavior/notebook_design/action_plan/retrieval/planner/speaker/
executor/commit/discord_bot/yuno_v2/writing/art/philosophy/app_design/codeを優先してください。
過去発言への明示的参照がある場合だけneeds_log_lookup=true, log_window=targetedにしてください。通常はfalse/minimalです。
JSON fields: reading, attention, note_hints[{note_id,relevance,use,reason}], candidate_actions, speaker_guidance,
needs_log_lookup, log_lookup_query, log_window, speaker_note。"""


class Planner:
    def __init__(self, client: OpenAIJsonClient):
        self.client = client

    async def plan(
        self,
        content: str,
        context: str,
        scopes: List[str],
        recent_history: List[Dict[str, str]],
        note_candidates: List[Dict[str, Any]],
        mind_context: Dict[str, Any],
    ) -> ActionPlan:
        payload = {
            "message": content,
            "context": context,
            "available_scopes": scopes,
            "mind_context": mind_context,
            "recent_history": recent_history[-4:],
            "pre_retrieval_candidates": note_candidates,
        }

        def fallback() -> Dict[str, Any]:
            lookup_terms = ("さっき", "前の案", "前回", "ログ", "あの発言")
            needs_log = any(term in content for term in lookup_terms)
            return {
                "reading": {"main_point": content[:300], "subtext": "mock planner", "do_not_flatten": []},
                "attention": {"topics": {"current_message": "high"}, "scopes": {"user": "high"}},
                "note_hints": [
                    {"note_id": item["note_id"], "relevance": "medium", "use": "possible", "reason": item["retrieval_reason"]}
                    for item in note_candidates[:3]
                ],
                "candidate_actions": [{"type": "speak", "confidence": "high", "brief": "ユーザーの発言へ自然に応答する"}],
                "speaker_guidance": {"depth": "short", "style": "natural", "avoid": ["未実装機能を実装済みと装う"]},
                "needs_log_lookup": needs_log,
                "log_lookup_query": content[:200] if needs_log else None,
                "log_window": "targeted" if needs_log else "minimal",
                "speaker_note": "現在の発言とmind contextを中心に返す",
            }

        raw = await self.client.complete_json([
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ], fallback)
        return ActionPlan.from_dict(raw)
