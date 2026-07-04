# 007: Read-only ToolReader minimum

## Goal

Add the first natural-language operation path only after permission, scope, and tool registry boundaries exist.

This task should support read-only status/health-style planning. It should not add write, restart, delete, backup, or arbitrary shell behavior.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/yuno_design_principles.md`
- `docs/next_direction.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/002_permission_service.md`
- `docs/codex_queue/003_scope_model.md`
- `docs/codex_queue/004_tool_registry.md`
- `docs/codex_queue/005_status_entry.md`

## Allowed scope

- `yuno/tools/`
- a small ToolReader / ActionPlanner module if needed
- read-only status/health service if already cleanly separated
- `tests/`
- minimal pipeline integration only if it is explicitly guarded and does not affect normal conversation unless a tool request is detected

## Do not touch

- Speaker persona or prompt
- CareReader prompt
- database schema
- listening behavior
- arbitrary shell execution
- arbitrary file reading
- write/restart/delete/restore operations
- raw log access

## Work to do

1. Add a minimal read-only ToolReader/ActionPlanner that can produce a `ToolPlan` for clearly operational phrases only.
2. Prefer cheap rule gating before any LLM call:
   - status
   - health
   - current settings summary
   - available tools
3. If the message is ordinary conversation, do not call ToolReader.
4. Execute only allowlisted read-only tools.
5. Route only sanitized `ToolResult` content to Speaker or a simple renderer. Do not modify the Speaker persona/prompt for this task.
6. Add tests for:
   - ordinary chat does not plan a tool
   - clear status request creates a read-only plan
   - permission denial blocks execution
   - raw/internal result is not exposed
   - ToolReader does not retry or loop

## Important constraints

- Default natural conversation must stay lightweight.
- Do not create an agent loop.
- Do not let ToolReader retry tools repeatedly.
- Do not use LLM for permission decisions.
- If a safe integration point is unclear, stop and report instead of changing pipeline broadly.

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

If the script is unavailable for some reason, run:

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
