# 003: Scope model skeleton

## Goal

Add a small scope model for future settings, memory visibility, and tool operations.

This should define where an operation applies. It should not decide who is allowed to perform it; that belongs to PermissionService.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/yuno_design_principles.md`
- `docs/next_direction.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/002_permission_service.md`

## Allowed scope

- `yuno/scope/` or a similarly small module
- `tests/`
- docs comments only if needed

## Do not touch

- database schema unless absolutely necessary; prefer pure value objects first
- Speaker persona or prompt
- CareReader prompt
- routing/listening behavior
- tool execution
- slash command surface

## Work to do

1. Define value types for operation scope:
   - global
   - server/guild
   - channel
   - stream
2. Keep user scope out unless a strong reason appears; document if deferred.
3. Provide small helpers for constructing scope from an incoming Discord message or stream metadata.
4. Keep scope separate from permission.
5. Add tests for:
   - global scope
   - guild/server scope
   - channel scope
   - stream scope
   - equality/serialization if implemented

## Important constraints

- Scope answers: where does this apply?
- Permission answers: who may do this?
- Do not mix the two.

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
