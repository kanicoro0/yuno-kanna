import json
from typing import Any, Dict, List

from yuno.actions.schema import ActionPlan, ExecutionResult, SpeakerOutput
from yuno.infra.openai_client import OpenAIJsonClient
from yuno.memory.prompt_view import speaker_memory_view


SPEAKER_SYSTEM_PROMPT = """あなたはDiscord bot『ゆの』のSpeakerです。
Executorから渡された範囲だけを使い、日本語で自然な返答を1通書いてください。記憶操作やscopeの再判断はしません。
JSONで reply と next_call{needed,type,reason,brief} を返してください。
typeはnone/followup/repair/second_thought。3回目は例外なので、通常はnoneにしてください。"""


class Speaker:
    def __init__(self, client: OpenAIJsonClient):
        self.client = client

    async def speak(self, content: str, plan: ActionPlan, execution: ExecutionResult) -> SpeakerOutput:
        payload = {
            "message": content,
            "reading": {
                "main_point": plan.reading.main_point,
                "subtext": plan.reading.subtext,
                "do_not_flatten": plan.reading.do_not_flatten,
            },
            "brief": execution.speaker_brief,
            "guidance": {
                "depth": plan.speaker_guidance.depth,
                "style": plan.speaker_guidance.style,
                "avoid": plan.speaker_guidance.avoid,
            },
            "memories": speaker_memory_view(execution.selected_memories),
        }

        def fallback() -> Dict[str, Any]:
            return {
                "reply": f"受け取ったよ。いまはmock Speakerで応答してる。\n\nあなたの発言: {content[:500]}",
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
