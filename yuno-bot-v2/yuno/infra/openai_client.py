import json
import logging
from typing import Any, Callable, Dict, List, Optional

from openai import AsyncOpenAI


logger = logging.getLogger(__name__)


class OpenAIJsonClient:
    """One narrow JSON boundary shared by Planner and Speaker."""

    def __init__(self, api_key: str, model: str):
        self.model = model
        self._client: Optional[AsyncOpenAI] = AsyncOpenAI(api_key=api_key) if api_key else None

    @property
    def is_mock(self) -> bool:
        return self._client is None

    async def complete_json(
        self,
        messages: List[Dict[str, str]],
        fallback: Callable[[], Dict[str, Any]],
    ) -> Dict[str, Any]:
        if self._client is None:
            return fallback()
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            value = json.loads(content)
            if not isinstance(value, dict):
                raise ValueError("OpenAI JSON response was not an object")
            return value
        except Exception as error:
            # Do not log request bodies, credentials, or raw provider responses.
            logger.warning("OpenAI call failed; using mock fallback (%s)", type(error).__name__)
            return fallback()
