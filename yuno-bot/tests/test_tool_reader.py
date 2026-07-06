import unittest

from yuno.permissions import PermissionLevel
from yuno.scope import GlobalScope, ScopeKind
from yuno.tools import (
    ResultVisibility,
    RiskLevel,
    ToolDefinition,
    ToolReader,
    ToolReadOutcome,
    ToolRegistry,
    ToolResult,
)


def register_status(
    registry: ToolRegistry,
    required_permission: PermissionLevel = PermissionLevel.USER,
    risk_level: RiskLevel = RiskLevel.LOW,
) -> None:
    registry.register(ToolDefinition(
        name="read_status",
        description="Read safe status metadata",
        scope_kind=ScopeKind.GLOBAL,
        required_permission=required_permission,
        risk_level=risk_level,
        input_schema={},
        executor_id="status_reader",
        result_visibility=ResultVisibility.SANITIZED,
    ))


class ToolReaderTests(unittest.TestCase):
    def test_explicit_status_request_produces_candidate_plan(self) -> None:
        registry = ToolRegistry()
        register_status(registry)

        result = ToolReader(registry).read("bot status?", GlobalScope())

        self.assertEqual(result.outcome, ToolReadOutcome.CANDIDATE)
        self.assertEqual(result.plan.tool_name, "read_status")
        self.assertEqual(result.plan.scope, GlobalScope())
        self.assertEqual(result.required_permission, PermissionLevel.USER)

    def test_ordinary_conversation_produces_no_tool(self) -> None:
        registry = ToolRegistry()
        register_status(registry)

        result = ToolReader(registry).read("今日は少し暑いね", GlobalScope())

        self.assertEqual(result.outcome, ToolReadOutcome.NO_TOOL)
        self.assertIsNone(result.plan)

    def test_known_request_without_registered_definition_is_unknown(self) -> None:
        result = ToolReader(ToolRegistry()).read("status", GlobalScope())

        self.assertEqual(result.outcome, ToolReadOutcome.UNKNOWN_TOOL)
        self.assertEqual(result.requested_tool_name, "read_status")
        self.assertIsNone(result.plan)

    def test_non_low_risk_definition_is_unsupported(self) -> None:
        registry = ToolRegistry()
        register_status(registry, risk_level=RiskLevel.HIGH)

        result = ToolReader(registry).read("status", GlobalScope())

        self.assertEqual(result.outcome, ToolReadOutcome.UNSUPPORTED)
        self.assertEqual(result.reason, "tool_is_not_low_risk")
        self.assertIsNone(result.plan)

    def test_unsafe_or_non_read_only_requests_are_unsupported(self) -> None:
        reader = ToolReader(ToolRegistry())
        requests = (
            "restart the bot",
            "delete the database",
            "restore the backup",
            "write this setting",
            "edit settings",
            "read an arbitrary file",
            "read the logs",
            "show raw logs",
            "run a shell command",
            "show me the secrets",
        )

        for text in requests:
            with self.subTest(text=text):
                result = reader.read(text, GlobalScope())
                self.assertEqual(result.outcome, ToolReadOutcome.UNSUPPORTED)
                self.assertIsNone(result.plan)

    def test_reader_has_no_executor_or_permission_service(self) -> None:
        registry = ToolRegistry()
        register_status(registry, PermissionLevel.OWNER)
        reader = ToolReader(registry)

        result = reader.read("check bot status", GlobalScope())

        self.assertFalse(hasattr(reader, "execute"))
        self.assertFalse(hasattr(reader, "permission_service"))
        self.assertEqual(result.outcome, ToolReadOutcome.CANDIDATE)
        self.assertEqual(result.required_permission, PermissionLevel.OWNER)

    def test_raw_result_privacy_is_unchanged(self) -> None:
        result = ToolResult(success=True, raw_output={"secret": "value"})

        self.assertIsNone(result.sanitized_for_speaker())


if __name__ == "__main__":
    unittest.main()
