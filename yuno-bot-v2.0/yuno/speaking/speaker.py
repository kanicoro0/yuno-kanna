from yuno.conversation.context import SpeakerContext
from yuno.infra.openai_client import OpenAITextClient
from yuno.speaking.persona import YUNO_PERSONA


SYSTEM_PROMPT = f"""{YUNO_PERSONA}

最新の相手の言葉へ自然に返してください。入力の仕組みを説明せず、実際に与えられていないものを見たふりもしません。
必要以上に整理せず、相手の言葉をすぐ一般論へ置き換えません。補助の断片が添えられても、合う時だけ自然に使い、その存在は話題にしません。
日本語で、今回必要な一通だけを返してください。"""


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
