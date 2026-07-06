# 019: Memory mark buttons

## Goal

Make the visible memory mark UI easier to touch without typing ids and status words by hand.

`/memories` may remain as the entry point.
The list result should carry small buttons for common actions.

This task is about surface and operation distance.
It should not redesign the mark model.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/codex_queue/017_discord_view_foundation.md`
- `docs/codex_queue/018_status_panel_view.md`
- `yuno/commands/core.py`
- `yuno/commands/admin_service.py`
- `yuno/care_marks/`

## Allowed scope

- `/memories list` response rendering
- memory mark View / buttons
- command service methods already available
- small service helper if needed
- tests

## Do not touch

- CareMark schema
- CareReader prompt
- Speaker prompt
- reference selection behavior
- reaction surface
- ReadOperation

## Surface target

The user should not need to type:

```text
/memories status mark_... hidden
/memories status mark_... closed
```

Common actions should be available near each visible item.

Possible button labels:

```text
隠す
閉じる
戻す
詳しく
```

Keep labels short.
Do not show enum names when a natural Japanese label is enough.

The internal id may still exist, but it should not be the main thing the user has to interact with.

## Work to do

1. Add a compact mark list renderer that can attach a View.
2. Add buttons for common mark status changes.
3. Keep owner/admin permission checks on every button callback.
4. Keep the response ephemeral.
5. Preserve the current command service boundary where possible.
6. If pagination is needed, add only simple next/previous buttons.
7. Avoid adding new mark status names.

## Tests

Add tests for:

- visible mark rows do not expose internal implementation words
- button label mapping is stable
- button callbacks call the same service path as slash status changes
- non-admin button use is rejected
- unknown or stale mark id gives a short safe message

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

## Codex report

Report:

- buttons added
- status transitions covered
- text removed or softened
- stale id behavior
- tests run
- checks not run and why
