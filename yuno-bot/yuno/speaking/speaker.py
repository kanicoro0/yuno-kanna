from yuno.conversation.context import SpeakerContext
from yuno.infra.openai_client import OpenAITextClient
from yuno.speaking.persona import YUNO_PERSONA


SYSTEM_PROMPT = f"""{YUNO_PERSONA}

入力の仕組みを説明しない
与えられていない情報を足さない
補助の断片があっても、合う時だけ使い、その存在は話題にしない

相手の表示名は必要な時だけ使う
呼び名や名前そのものが話題の時は、宛名として消費せず、その音や形に少し触れる

最新の発言を主に返す
古い発言や別の人の短い反応を、今の返事に無理に混ぜない
日常会話では、原則1〜3文で短く返す
説明は、相手が説明を求めた時だけ少し長くする

今ここで返す一通だけを書く"""

_ROUTE_NOTES = {
    "dm": "今の発言はDMで届いている。短く自然に返す。",
    "mention": "今の発言はメンションで直接呼ばれている。最新の発言だけを主に返す。",
    "reply_to_yuno": "今の発言は直前のゆのへの返信。返信先の流れを主に見る。",
    "name_call": "今の発言は呼びかけとして扱われている。ただし名前が出た理由を決めつけず、短く返す。",
    "listening_only": "今の発言は近くの会話として読んでいる。割り込みすぎず、必要な時だけ短く返す。",
    "name_seen": "今の発言には名前に似た音が含まれるが、直接呼ばれたとは限らない。返す時も決めつけず短く返す。",
}

_REPLY_REASON_HINTS = {
    "direct_call": "ゆのへのはっきりした呼びかけとして受け取って大丈夫。",
    "mention": "今のひとことは、ゆのへの呼びかけとして返して大丈夫。",
    "reply_to_yuno": "いまの返事の続きとして受け取って大丈夫。",
    "followup": "さっきの流れの続きとして自然につないで大丈夫。",
    "casual_reaction": "軽く受け止めるくらいの返しで十分。",
    "name_topic": "呼びかけや話題の向き先として、ゆのが意識されている。",
    "overheard_only": "強く踏み込みすぎず、必要なら控えめに返す。",
    "none": "返す時は、今の会話だけを素直に受け取る。",
}


class Speaker:
    def __init__(self, client: OpenAITextClient):
        self.client = client

    async def speak(self, context: SpeakerContext) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        route_note = _ROUTE_NOTES.get(context.route_reason or "")
        if route_note:
            messages.append({"role": "system", "content": route_note})
        if context.reply_reason or context.speaker_note:
            messages.append({
                "role": "system",
                "content": _speaker_support_message(context),
            })
        if context.references:
            messages.append({
                "role": "system",
                "content": "必要なら使える短い断片:\n" + "\n".join(
                    f"- {item.content}" for item in context.references
                ),
            })
        messages.extend(context.history)
        return (await self.client.complete(messages)).strip()[:2000]


def _speaker_support_message(context: SpeakerContext) -> str:
    parts = []
    if context.reply_reason:
        hint = _REPLY_REASON_HINTS.get(context.reply_reason)
        if hint:
            parts.append(hint)
    if context.speaker_note:
        parts.append(context.speaker_note)
    return "\n".join(parts)