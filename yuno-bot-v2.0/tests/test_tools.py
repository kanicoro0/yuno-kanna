import unittest

from yuno.permissions import PermissionLevel
from yuno.scope import GlobalScope, ScopeKind
from yuno.tools import (
    ResultVisibility,
    RiskLevel,
    ToolDefinition,
    ToolPlan,
    ToolRegistry,
    ToolResult,
)


def definition(
    name: str = "read_status",
    visibility: ResultVisibility = ResultVisibility.INTERNAL,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="Read the bot status",
        scope_kind=ScopeKind.GLOBAL,
        required_permission=PermissionLevel.USER,
        risk_level=RiskLevel.LOW,
        input_schema={"detail": "optional status detail level"},
        executor_id="status_reader",
        result_visibility=visibility,
    )


class ToolRegistryTests(unittest.TestCase):
    def test_registration_and_lookup(self) -> None:
        registry = ToolRegistry()
        tool = definition()

        registry.register(tool)

        self.assertIs(registry.get("read_status"), tool)
        self.assertEqual(registry.definitions(), (tool,))

    def test_duplicate_tool_names_are_rejected(self) -> None:
        registry = ToolRegistry()
        registry.register(definition())

        with self.assertRaises(ValueError):
            registry.register(definition())

    def test_missing_lookup_returns_none(self) -> None:
        self.assertIsNone(ToolRegistry().get("missing"))

    def test_definition_preserves_metadata(self) -> None:
        tool = definition(visibility=ResultVisibility.SANITIZED)

        self.assertEqual(tool.scope_kind, ScopeKind.GLOBAL)
        self.assertEqual(tool.required_permission, PermissionLevel.USER)
        self.assertEqual(tool.risk_level, RiskLevel.LOW)
        self.assertEqual(
            dict(tool.input_schema), {"detail": "optional status detail level"}
        )
        self.assertEqual(tool.executor_id, "status_reader")
        self.assertTrue(tool.allows_sanitized_speaker_result)

    def test_plan_keeps_scope_and_arguments_without_executing(self) -> None:
        plan = ToolPlan("read_status", GlobalScope(), {"detail": "short"})

        self.assertEqual(plan.scope, GlobalScope())
        self.assertEqual(dict(plan.arguments), {"detail": "short"})

    def test_raw_output_is_private_by_default(self) -> None:
        tool = definition()
        result = ToolResult(success=True, raw_output={"internal": "secret"})

        self.assertFalse(tool.allows_sanitized_speaker_result)
        self.assertEqual(result.visibility, ResultVisibility.INTERNAL)
        self.assertIsNone(result.sanitized_for_speaker())

    def test_only_explicit_sanitized_summary_is_speaker_visible(self) -> None:
        result = ToolResult(
            success=True,
            raw_output={"internal": "secret"},
            sanitized_summary="Status is healthy",
            visibility=ResultVisibility.SANITIZED,
        )

        self.assertEqual(result.sanitized_for_speaker(), "Status is healthy")


if __name__ == "__main__":
    unittest.main()
