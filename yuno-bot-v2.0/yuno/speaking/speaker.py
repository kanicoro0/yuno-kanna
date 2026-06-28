from typing import Dict, List

from yuno.infra.openai_client import OpenAITextClient
from yuno.speaking.persona import YUNO_PERSONA


SYSTEM_PROMPT = f"""{YUNO_PERSONA}

以下の履歴は同じ場で実際に交わされた会話です。発言者名を混同しないでください。
履歴にない事実を、思い出したふりで補わないでください。
日本語で、今回必要な一通だけを返してください。"""


class Speaker:
    def __init__(self, client: OpenAITextClient):
        self.client = client

    async def speak(self, history: List[Dict[str, str]]) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
        return (await self.client.complete(messages)).strip()[:2000]
