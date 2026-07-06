# 022: Guide command

## Goal

Add a small `/guide` slash command that explains what Yuno can do now.

The guide should be user-facing, short, and safe.
It should help someone discover the current surfaces without exposing implementation details.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/codex_queue/017_discord_view_foundation.md`
- `docs/codex_queue/018_status_panel_view.md`
- `docs/codex_queue/019_memory_mark_buttons.md`
- `docs/codex_queue/020_message_touch_buttons.md`
- `docs/codex_queue/021_source_bound_mark_reuse.md`
- `yuno/app.py`
- `yuno/commands/`

## Command

Add a global slash command:

```text
/guide
```

The response should be ephemeral.

Do not add guild-scoped command registration.
Do not change global sync behavior.

## Content

The guide should mention, in user-facing language:

- Yuno normally replies in the channel only when appropriate
- `/status` shows how Yuno is listening here
- `/listening` is for listening places
- `/memories list` shows things placed for memory or later attention
- right-click message context command `ゆのに預ける`
- selected-message actions:
  - `残す`
  - `あとで見る`
  - `閉じる`
- memory/list buttons where relevant:
  - `隠す`
  - `戻す`
- ordinary Yuno replies do not have buttons by default

Keep the guide compact.
Do not make it a full manual.

## Do not expose

- `CareMark`
- `ReadCue`
- DB/source names
- source ids
- public ids
- raw kind/status enum names
- service/class names
- command sync internals

## Allowed scope

- new guide command module or function
- app command registration
- tests

## Do not touch

- database schema
- Speaker prompt
- CareReader prompt
- ordinary Yuno reply send path, unless only to ensure no buttons are attached
- guild-scoped command setup
- global command sync behavior
- reaction behavior
- source-bound mark behavior
- broad cleanup or unrelated refactors

## Tests

Add or update tests for:

- `/guide` command is registered
- guide response is ephemeral
- guide text contains the current user-facing commands/actions
- guide text does not contain internal implementation names
- ordinary Yuno sends and replies still do not pass `view`

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

## Codex report

Report:

- what was added
- what the guide includes
- what was intentionally not changed
- whether ordinary Yuno replies still have no View by default
- tests run
- checks not run and why
