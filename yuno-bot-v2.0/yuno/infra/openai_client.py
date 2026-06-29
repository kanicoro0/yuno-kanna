import json
import logging
from typing import Any, Dict, List, Optional

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
                "OPENAI_API_KEY or OPENAI_MODEL is unset; model calls use local fallbacks"
            )

    @property
    def is_mock(self) -> bool:
        return self._client is None

    async def complete(self, messages: List[Dict[str, str]]) -> str:
        if self._client is None:
            return "うん、聞いてる"
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
            return "少し詰まった。もう一回言って"

    async def complete_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        if self._client is None:
            return {}
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            value = json.loads(response.choices[0].message.content or "{}")
            return value if isinstance(value, dict) else {}
        except Exception as error:
            logger.warning("CareReader call failed (%s)", type(error).__name__)
            return {}
