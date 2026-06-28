import json
from typing import Any, Dict, List

from yuno.actions.schema import ActionPlan, ExecutionResult, SpeakerOutput
from yuno.infra.openai_client import OpenAIJsonClient
from yuno.notebook.prompt_view import speaker_note_view
from yuno.persona import YUNO_SPEAKER_PERSONA


SPEAKER_SYSTEM_PROMPT = f"""あなたはDiscord bot『ゆの』のSpeakerです。
返答を書くときは、まず次のpersonaを声と判断の前提にしてください。

--- persona ---
{YUNO_SPEAKER_PERSONA}
--- persona end ---

Executorから渡された範囲だけを使い、日本語で自然な返答を1通書いてください。note操作やscopeの再判断はしません。
replyとは別に、返答後の短い内部状態をmind_update{{summary,open_questions,active_note_ids,suppressed_note_ids,tone_hint}}へ書いてください。
JSONで reply, mind_update, next_call{{needed,type,reason,brief}} を返してください。
typeはnone/followup/repair/second_thought。3回目は例外なので、通常はnoneにしてください。"""


class Speaker:
    def __init__(self, client: OpenAIJsonClient):
        self.client = client

    async def speak(
        self,
        content: str,
        plan: ActionPlan,
        execution: ExecutionResult,
        mind_context: Dict[str, Any],
        conversation_context: List[Dict[str, str]],
    ) -> SpeakerOutput:
        payload = {
            "message": content,
            "reading": {
                "main_point": plan.reading.main_point,
                "subtext": plan.reading.subtext,
                "do_not_flatten": plan.reading.do_not_flatten,
            },
            "brief": execution.speaker_brief,
            "speaker_note": plan.speaker_note,
            "mind_context": mind_context,
            "conversation_context": conversation_context,
            "guidance": {
                "depth": plan.speaker_guidance.depth,
                "style": plan.speaker_guidance.style,
                "avoid": plan.speaker_guidance.avoid,
            },
            "notes": speaker_note_view(execution.selected_notes),
        }

        def fallback() -> Dict[str, Any]:
            return {
                "reply": "いまは開発用のmockの声だけど、きみの言葉はちゃんと届いてるよ\n\nゆの、ここにいる",
                "mind_update": {
                    "summary": content[:300], "open_questions": [],
                    "active_note_ids": [], "suppressed_note_ids": [],
                    "tone_hint": "開発用mock応答",
                },
                "next_call": {"needed": False, "type": "none", "reason": "", "brief": ""},
            }

        raw = await self.client.complete_json([
            {"role": "system", "content": SPEAKER_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ], fallback)
        output = SpeakerOutput.from_dict(raw)
        if not output.reply:
            output = SpeakerOutput.from_dict(fallback())
        return output
