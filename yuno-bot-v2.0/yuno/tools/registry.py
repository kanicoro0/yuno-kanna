from typing import Dict, Optional, Tuple

from yuno.tools.models import ToolDefinition


class ToolRegistry:
    """Metadata registry only; it does not execute tools."""

    def __init__(self) -> None:
        self._definitions: Dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"tool already registered: {definition.name}")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._definitions.get(name)

    def definitions(self) -> Tuple[ToolDefinition, ...]:
        return tuple(self._definitions.values())
