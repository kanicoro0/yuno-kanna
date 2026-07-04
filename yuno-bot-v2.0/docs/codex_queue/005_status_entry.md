# 005: Status entry consolidation

## Goal

Prepare `/status` as the low-friction status entry without expanding the command surface.

This task should improve status visibility carefully. It should not turn status into a large management UI.

## Read first

- `docs/yuno_design_principles.md`
- `docs/next_direction.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/002_permission_service.md`
- `docs/codex_queue/003_scope_model.md`
- `docs/codex_queue/004_tool_registry.md`

## Allowed scope

- existing status command implementation
- small read-only status service if useful
- `tests/`
- docs comments only if needed

## Do not touch

- Speaker persona or prompt
- CareReader prompt
- routing/listening behavior
- database schema
- memory/attention mutation behavior
- new command groups, unless there is a strong documented reason
- tool execution

## Work to do

1. Review current `/status` behavior.
2. Keep it read-only.
3. If useful, show a concise split between:
   - general user-visible status
   - admin/owner-visible operational status
4. Include only safe information:
   - listening channel state
   - configured call names
   - model name if already safe to expose
   - database path only for owner/admin if exposed at all
   - registered tool names only if a registry already exists
5. Do not expose secrets, raw paths, tracebacks, or internal scores.
6. Add tests if a service or renderer is added.

## Important constraints

- `/status` is an entry point, not a dumping ground.
- Do not add `/memory`, `/attention`, `/interest`, or `/listening` features here.
- Do not change normal conversation behavior.

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
