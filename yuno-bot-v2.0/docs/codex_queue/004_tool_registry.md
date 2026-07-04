# 004: Tool definition and registry skeleton

## Goal

Add the non-executing skeleton for future tools.

This task should define tool metadata and registration. It should not run tools yet.

## Read first

- `docs/yuno_design_principles.md`
- `docs/next_direction.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/002_permission_service.md`
- `docs/codex_queue/003_scope_model.md`

## Allowed scope

- `yuno/tools/`
- `tests/`
- docs comments only if needed

## Do not touch

- Speaker persona or prompt
- CareReader prompt
- `ConversationPipeline.process` behavior
- database schema
- Discord commands, unless only adding a non-invasive future-facing import is unavoidable
- actual shell/file/log/service execution

## Work to do

1. Add value objects for:
   - `ToolDefinition`
   - `ToolPlan`
   - `ToolResult`
   - risk level
   - result visibility / whether raw result may be shown to Speaker
2. Add a simple `ToolRegistry` that can register and look up definitions by name.
3. Require metadata for each tool definition:
   - name
   - description
   - scope kind
   - required permission
   - risk level
   - input schema or minimal parameter description
   - executor identifier or placeholder
   - whether raw output may be exposed to Speaker
4. Add tests for registration, duplicate names, missing lookup, and metadata preservation.

## Important constraints

- Do not add arbitrary shell execution.
- Do not read arbitrary files.
- Do not add restart/delete/write actions.
- Do not let LLM decide permissions.
- Do not pass raw logs or secrets to Speaker.

## Checks

Run:

```bash
python -m compileall main.py yuno tests
python -m unittest discover -s tests
python -c "from yuno.app import create_bot; bot=create_bot(); print('bot ok')"
```

## Codex report

Report:

- added things
- replaced things
- remaining legacy/debug things
- next deletion candidates
- checks run
