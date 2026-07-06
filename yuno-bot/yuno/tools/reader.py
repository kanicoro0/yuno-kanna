from dataclasses import dataclass
from enum import Enum
import re
import unicodedata
from typing import Optional

from yuno.permissions import PermissionLevel
from yuno.scope import OperationScope
from yuno.tools.models import RiskLevel, ToolPlan
from yuno.tools.registry import ToolRegistry


class ToolReadOutcome(str, Enum):
    NO_TOOL = "no_tool"
    UNKNOWN_TOOL = "unknown_tool"
    CANDIDATE = "candidate"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ToolReadResult:
    outcome: ToolReadOutcome
    requested_tool_name: Optional[str] = None
    plan: Optional[ToolPlan] = None
    required_permission: Optional[PermissionLevel] = None
    reason: Optional[str] = None


class ToolReader:
    """Conservatively recognizes plans; it never authorizes or executes them."""

    _INTENTS = {
        "status": "read_status",
        "bot status": "read_status",
        "listening status": "read_status",
        "show status": "read_status",
        "check status": "read_status",
        "check bot status": "read_status",
        "what is the bot status": "read_status",
        "what's the bot status": "read_status",
        "ステータス": "read_status",
        "botの状態": "read_status",
        "聞き耳の状態": "read_status",
        "what can you check": "list_tools",
        "available tools": "list_tools",
        "show available tools": "list_tools",
        "何を確認できる": "list_tools",
    }

    _UNSUPPORTED_PATTERNS = (
        r"^(?:please\s+)?(?:restart|delete|restore|write)\b",
        r"\b(?:can you|could you|please)\s+(?:restart|delete|restore|write)\b",
        r"\b(?:edit|change|update)\s+(?:the\s+)?settings?\b",
        r"\b(?:read|open|show)\s+(?:an?\s+|the\s+|my\s+)?(?:arbitrary\s+)?files?\b",
        r"\b(?:read|show|get)\s+(?:the\s+)?(?:raw\s+)?logs?\b",
        r"\b(?:run|execute|open)\s+(?:a\s+|the\s+)?shell(?:\s+commands?)?\b",
        r"\b(?:show|read|get|reveal)\s+(?:me\s+)?(?:the\s+)?(?:secrets?|tokens?|passwords?|env)\b",
        r"(?:再起動|削除|復元して|設定を(?:編集|変更)|ファイルを(?:読|開)|生ログ|シェル|秘密を見せ|トークンを見せ)",
    )

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def read(self, user_text: str, scope: OperationScope) -> ToolReadResult:
        normalized = _normalize(user_text)
        if not normalized:
            return ToolReadResult(ToolReadOutcome.NO_TOOL)
        if any(re.search(pattern, normalized) for pattern in self._UNSUPPORTED_PATTERNS):
            return ToolReadResult(
                ToolReadOutcome.UNSUPPORTED, reason="unsafe_or_non_read_only_request"
            )

        tool_name = self._INTENTS.get(normalized)
        if tool_name is None:
            return ToolReadResult(ToolReadOutcome.NO_TOOL)

        definition = self.registry.get(tool_name)
        if definition is None:
            return ToolReadResult(
                ToolReadOutcome.UNKNOWN_TOOL, requested_tool_name=tool_name
            )
        if definition.risk_level is not RiskLevel.LOW:
            return ToolReadResult(
                ToolReadOutcome.UNSUPPORTED,
                requested_tool_name=tool_name,
                required_permission=definition.required_permission,
                reason="tool_is_not_low_risk",
            )
        if definition.scope_kind is not scope.kind:
            return ToolReadResult(
                ToolReadOutcome.UNSUPPORTED,
                requested_tool_name=tool_name,
                required_permission=definition.required_permission,
                reason="scope_mismatch",
            )
        return ToolReadResult(
            ToolReadOutcome.CANDIDATE,
            requested_tool_name=tool_name,
            plan=ToolPlan(tool_name, scope),
            required_permission=definition.required_permission,
        )


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold().strip()
    text = re.sub(r"[?!。！？]+$", "", text).strip()
    return re.sub(r"\s+", " ", text)
