import logging
from typing import Dict, List, Optional

from openai import AsyncOpenAI


logger = logging.getLogger(__name__)


class OpenAITextClient:
    """A narrow text-only boundary for the Speaker."""

    def __init__(self, api_key: str, model: str):
        self.model = model
        self._client: Optional[AsyncOpenAI] = (
            AsyncOpenAI(api_key=api_key) if api_key and model else None
        )
        if self._client is None:
            logger.warning(
                "OPENAI_API_KEY or OPENAI_MODEL is unset; Speaker uses a local fallback"
            )

    @property
    def is_mock(self) -> bool:
        return self._client is None

    async def complete(self, messages: List[Dict[str, str]]) -> str:
        if self._client is None:
            return "うん、聞いてるよ\n\nゆの、ここにいる"
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            reply = (response.choices[0].message.content or "").strip()
            if not reply:
                raise ValueError("Speaker returned an empty reply")
            return reply
        except Exception as error:
            logger.warning("Speaker call failed (%s)", type(error).__name__)
            return "ちょっと言葉がほどけちゃった\n\nもう一度、聞かせて"
