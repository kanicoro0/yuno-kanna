from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional

from yuno.permissions import PermissionLevel
from yuno.scope import OperationScope, ScopeKind


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResultVisibility(str, Enum):
    INTERNAL = "internal"
    SANITIZED = "sanitized"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    scope_kind: ScopeKind
    required_permission: PermissionLevel
    risk_level: RiskLevel
    input_schema: Mapping[str, str]
    executor_id: str
    result_visibility: ResultVisibility = ResultVisibility.INTERNAL

    def __post_init__(self) -> None:
        for field_name in ("name", "description", "executor_id"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")
        object.__setattr__(
            self, "input_schema", MappingProxyType(dict(self.input_schema))
        )

    @property
    def allows_sanitized_speaker_result(self) -> bool:
        return self.result_visibility is ResultVisibility.SANITIZED


@dataclass(frozen=True)
class ToolPlan:
    tool_name: str
    scope: OperationScope
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tool_name.strip():
            raise ValueError("tool_name must not be empty")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True)
class ToolResult:
    success: bool
    raw_output: Any = None
    sanitized_summary: Optional[str] = None
    visibility: ResultVisibility = ResultVisibility.INTERNAL

    def sanitized_for_speaker(self) -> Optional[str]:
        if self.visibility is not ResultVisibility.SANITIZED:
            return None
        return self.sanitized_summary
