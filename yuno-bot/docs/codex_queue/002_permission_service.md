# 002: PermissionService skeleton

## Goal

Add the permission boundary used by both slash commands and future natural-language tool operations.

This should be a skeleton with tests. It should not change normal conversation behavior.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/yuno_design_principles.md`
- `docs/next_direction.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/001_review_current_structure.md`

## Allowed scope

- `yuno/permissions/`
- `tests/`
- `yuno/config.py` and `.env.example` only if needed to add an explicit owner id setting
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
5. If owner identity is configurable, use an explicit setting such as `OWNER_USER_IDS`; do not hardcode a user id.
6. Add tests for:
   - owner allowed for owner-only actions
   - guild admin allowed for guild-admin actions
   - normal user denied for admin actions
   - missing guild context does not accidentally grant guild permission
   - no configured owner does not accidentally grant owner permission

## Important constraints

- Do not ask an LLM to decide permissions.
- Do not perform any tool execution.
- Do not add new slash commands for this task.
- Do not add DB tables.
- Do not infer owner status from display names or usernames.

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
