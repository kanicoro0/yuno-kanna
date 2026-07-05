# 021: Source-bound mark reuse and close action

## Goal

Resolve the remaining selected-message mark behavior after queue 020.

The selected-message panel should not create duplicate marks for the same saved Discord message.
It should also show `閉じる` only when the selected message is already tied to an open attention mark.

This task keeps the selected-message action model small:

```text
right click = touch a selected message
slash command = entry point, status check, whole-bot settings
button panel = continue editing the thing already opened
ordinary Yuno reply = spoken reply, no View by default
```

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/codex_queue/017_discord_view_foundation.md`
- `docs/codex_queue/018_status_panel_view.md`
- `docs/codex_queue/019_memory_mark_buttons.md`
- `docs/codex_queue/020_message_touch_buttons.md`
- `yuno/commands/message_actions.py`
- `yuno/commands/admin_service.py`
- `yuno/care_marks/`

## Duplicate rule

A duplicate selected-message mark is determined by:

```text
stream_id + source_message_id + kind
```

Do not use message text alone to infer identity.

## Behavior: `残す`

- If no memory mark exists for the selected message, create a memory draft using the existing path.
- If a memory draft or active mark already exists, do not create a duplicate.
- If a memory hidden mark exists, change it to draft.

A hidden memory changed by `残す` is not being restored to its original state.
It is being placed as a draft because the user pressed `残す` now.

Suggested user-facing result text:

```text
このメッセージを残したよ
もう残してあるよ
また残したよ
```

## Behavior: `あとで見る`

- If no attention mark exists for the selected message, create an attention open mark using the existing path.
- If an attention open mark already exists, do not create a duplicate.
- If an attention closed or hidden mark exists, change it to open.

A closed or hidden attention changed by `あとで見る` is not being restored to history.
It is being opened because the user pressed `あとで見る` now.

Suggested user-facing result text:

```text
あとで見られるように置いたよ
もう置いてあるよ
また見られるようにしたよ
```

## Behavior: `閉じる`

Show `閉じる` only when the selected message is tied to an attention/open mark.

Pressing `閉じる` changes that mark to closed.

If older data has multiple open attention marks for the same selected message, close only the newest one.
Do not close all matching marks.
Do not close unrelated attention marks.
Do not infer a target from text alone.

## Repository / service work

Add a small repository/service method to find care marks by:

```text
stream_id
source_message_id
kind
```

Prefer returning newest first if more than one exists.

Keep existing public-id based paths working.
Keep schema unchanged.

## Allowed scope

- selected-message action service behavior
- selected-message panel button selection
- small repository/service lookup methods
- tests

## Do not touch

- database schema
- Speaker prompt
- CareReader prompt
- ordinary Yuno reply send path, unless only to ensure no buttons are attached
- guild-scoped command registration
- global command sync behavior
- reaction behavior
- broad cleanup or unrelated refactors

## UI safety

The selected-message panel should keep using safe user-facing text.

Do not expose:

- `CareMark`
- `ReadCue`
- DB/source names
- `source_message_id`
- `public_id`
- raw kind/status enum names
- implementation class names

Successful actions should edit the existing ephemeral panel where practical.
Stale or expired buttons should fail safely.
Missing, deleted, inaccessible, unstored, or cross-stream targets should still fail safely.

## Tests

Add or update tests for:

- repeated `残す` on the same selected message does not create duplicate memory marks
- repeated `あとで見る` on the same selected message does not create duplicate attention marks
- hidden memory + `残す` becomes draft
- closed attention + `あとで見る` becomes open
- hidden attention + `あとで見る` becomes open
- `閉じる` appears only when the selected message has an open attention mark
- `閉じる` closes only the selected message's newest open attention mark
- unrelated marks are not affected
- ordinary Yuno sends and replies still do not pass `view`
- no schema or command sync changes are introduced

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

## Codex report

Report:

- what was added
- what reuse rules were implemented
- how `閉じる` is targeted
- what was intentionally not changed
- whether ordinary Yuno replies still have no View by default
- tests run
- checks not run and why
