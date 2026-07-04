# 002: PermissionService skeleton

## Goal

Add the permission boundary used by both slash commands and future natural-language tool operations.

This should be a skeleton with tests. It should not change normal conversation behavior.

## Read first

- `docs/yuno_design_principles.md`
- `docs/next_direction.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/001_review_current_structure.md`

## Allowed scope

- `yuno/permissions/`
- `tests/`
- small imports only if needed
- docs comments only if needed

## Do not touch

- Speaker persona or prompt
- CareReader prompt
- `ConversationPipeline.process` behavior
- database schema
- existing command behavior, except if adding a non-invasive shared helper is clearly necessary
- tool execution
- arbitrary shell or file access

## Work to do

1. Add a small permission model for future actions:
   - owner
   - guild_admin
   - user
2. Keep Discord permissions separate from owner-level trust.
3. Add a `PermissionService` or equivalent class that can answer whether an actor may perform an action.
4. Make the service usable from both command handlers and future ToolReader/ToolExecutor paths.
5. Add tests for:
   - owner allowed for owner-only actions
   - guild admin allowed for guild-admin actions
   - normal user denied for admin actions
   - missing guild context does not accidentally grant guild permission

## Important constraints

- Do not ask an LLM to decide permissions.
- Do not perform any tool execution.
- Do not add new slash commands for this task.
- Do not add DB tables.

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
