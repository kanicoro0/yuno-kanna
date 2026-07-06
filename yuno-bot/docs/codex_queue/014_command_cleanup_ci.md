# 014: Command cleanup + CI

## Goal

Clean up command surfaces after the CareMark / ReadCue transition, and make the standard check command run in CI.

This task should not add new bot abilities. It should remove or consolidate old visible surfaces that became misleading after CareMark replaced MemoryMark / AttentionItem / InterestTerm.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/yuno_design_principles.md`
- `docs/next_direction.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/011_schema_reset_caremark_readcue.md`
- `docs/codex_queue/012_care_reader_service_rewrite.md`
- `docs/codex_queue/013_context_reference_rewrite.md`
- `yuno/app.py`
- `yuno/commands/`
- `scripts/check_yuno.py`

## Allowed scope

- `yuno/commands/`
- `yuno/app.py`
- docs referencing old command names
- GitHub Actions workflow for `scripts/check_yuno.py`
- tests

## Do not touch

- Speaker persona or prompt
- CareReader prompt
- database schema except import cleanup
- Discord runtime / TurnBuffer behavior
- tool execution
- ReadOperation

## Work to do

1. Remove or clearly legacy-hide `/interest` if it still exists.
2. Replace `/memory` and `/attention` surfaces with the thinnest CareMark-facing surface if needed.
3. Avoid adding many slash commands.
4. Keep command handlers thin:
   - permission / service / result / renderer
5. Add or update CI so `python scripts/check_yuno.py` runs on pull requests.
6. Make docs match the new command surface.
7. Report remaining legacy/debug entry points.

## Tests

Add tests for:

- app creation still succeeds
- old command imports are gone or intentionally legacy
- CareMark command/service path works if a command is provided
- CI workflow references the standard check script

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

## Codex report

Report:

- added things
- replaced things
- command surfaces removed or kept as legacy
- remaining legacy/debug things
- next deletion candidates
- checks run
- checks not run and why
