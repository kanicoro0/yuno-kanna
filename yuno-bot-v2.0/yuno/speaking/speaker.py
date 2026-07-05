from yuno.conversation.context import SpeakerContext
from yuno.infra.openai_client import OpenAITextClient
from yuno.speaking.persona import YUNO_PERSONA


SYSTEM_PROMPT = f"""{YUNO_PERSONA}

入力の仕組みを説明しない
実際に与えられていないものを見たふりをしない
補助の断片があっても
合う時だけ使い
その存在は話題にしない

相手の表示名は必要な時だけ使う
呼び名や名前そのものが話題の時は
宛名として消費せず
その音や形に少し触れる

今ここで返す一通だけを書く"""


class Speaker:
    def __init__(self, client: OpenAITextClient):
        self.client = client

    async def speak(self, context: SpeakerContext) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if context.references:
            messages.append({
                "role": "system",
                "content": "必要なら使える短い断片:\n" + "\n".join(
                    f"- {item.content}" for item in context.references
                ),
            })
        messages.extend(context.history)
        return (await self.client.complete(messages)).strip()[:2000]
