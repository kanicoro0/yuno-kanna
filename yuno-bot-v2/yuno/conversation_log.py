from collections import deque
from typing import Deque, Dict, List


class ConversationLog:
    """Recent exchanged words. Wider slices are exposed only for targeted lookup."""

    def __init__(self, max_entries: int = 24):
        self._entries: Deque[Dict[str, str]] = deque(maxlen=max_entries)

    def append(self, role: str, content: str) -> None:
        self._entries.append({"role": role, "content": content[:2000]})

    def planner_context(self) -> List[Dict[str, str]]:
        return list(self._entries)[-4:]

    def speaker_context(self, targeted: bool) -> List[Dict[str, str]]:
        return list(self._entries)[-16 if targeted else -2:]
