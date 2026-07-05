# 020: Selected message action panel

## Goal

Add a small action surface for a selected Discord message without attaching buttons to ordinary Yuno replies.

Yuno's normal replies should stay light.
Buttons should live in explicit panels, command responses, or a targeted message context command, not on every spoken reply.

The goal is to reduce slash-command typing while keeping the channel surface quiet.

This task is not another memory list panel.
It is for touching a message that is not necessarily a mark yet.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/codex_queue/017_discord_view_foundation.md`
- `docs/codex_queue/018_status_panel_view.md`
- `docs/codex_queue/019_memory_mark_buttons.md`
- `docs/codex_queue/016_reaction_surface.md`
- `yuno/commands/`
- `yuno/care/`
- `yuno/care_marks/`

## Allowed scope

- a global Discord message context command
- ephemeral selected-message action panel
- small callbacks that call existing service methods
- tests

## Do not touch

- ordinary Yuno reply send path, unless only to ensure no buttons are attached
- Speaker prompt
- CareReader prompt
- routing rules
- database schema unless absolutely necessary
- arbitrary read operations
- guild-scoped command registration
- global command sync behavior beyond registering the new global command

## Surface target

Do not attach a View to normal Yuno replies by default.

Use a global message context command as the entry point if Discord support is straightforward.
It should open a small ephemeral panel for the selected message.

Prefer explicit UI surfaces:

```text
/status panel
/memories list panel
message context action for a selected message
```

Possible labels:

```text
残す
あとで見る
閉じる
隠す
戻す
```

The labels should remain short and not look like an admin console.

The user should not need to know a mark id, kind, or status enum for common actions.

## Work to do

1. Add a global message context command, if Discord support is straightforward.
2. Open an ephemeral panel for the selected message.
3. Keep ordinary Yuno replies free of buttons.
4. Wire buttons to existing CareMark / ReadCue service paths where possible.
5. Keep failure safe and ephemeral.
6. Avoid duplicating reaction behavior.
7. Do not create hidden long-term state just because a button was shown.
8. Do not add guild-scoped commands for this task.

## Suggested first condition

Start from a selected-message context action, not from a Yuno reply.

A safe first version may offer only a small set of actions such as:

```text
残す
あとで見る
閉じる
```

If one of those actions cannot be wired cleanly to an existing service path, leave it out instead of inventing new state.

## Tests

Add tests for:

- ordinary Yuno replies do not receive buttons by default
- global message context command is registered without guild-scoped command setup
- selected-message panel can render a small button set
- callbacks use existing service paths
- stale button use gives a short safe message
- button failures do not roll back sent messages or stored conversation logs

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

## Codex report

Report:

- global message context command added or intentionally skipped
- buttons added
- service paths used
- ordinary reply surface left untouched
- guild-scoped commands left untouched
- tests run
- checks not run and why
