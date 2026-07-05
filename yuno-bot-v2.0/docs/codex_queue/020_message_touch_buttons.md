# 020: Message action panel

## Goal

Add a small message-related action surface without attaching buttons to ordinary Yuno replies.

Yuno's normal replies should stay light.
Buttons should live in explicit panels, command responses, or targeted message actions, not on every spoken reply.

The goal is to reduce slash-command typing while keeping the channel surface quiet.

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

- command panels
- targeted message action entry points, if Discord support is straightforward
- small callbacks that call existing service methods
- tests

## Do not touch

- ordinary Yuno reply send path, unless only to ensure no buttons are attached
- Speaker prompt
- CareReader prompt
- routing rules
- database schema unless absolutely necessary
- arbitrary read operations
- global slash command sync behavior

## Surface target

Do not attach a View to normal Yuno replies by default.

Prefer explicit UI surfaces:

```text
/status panel
/memories list panel
message context action, if added later
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

1. Decide whether this task should extend `/memories` panels or add a targeted message action entry point.
2. Keep ordinary Yuno replies free of buttons.
3. Wire buttons to existing CareMark / ReadCue service paths where possible.
4. Keep failure safe and ephemeral.
5. Avoid duplicating reaction behavior.
6. Do not create hidden long-term state just because a button was shown.

## Suggested first condition

Start from an explicit panel, not from a Yuno reply.

A safe first version may extend the memory mark panel with actions such as:

```text
閉じる
隠す
戻す
```

If a targeted message action is added, it should open a small ephemeral panel for that selected message rather than modifying Yuno's spoken reply surface.

## Tests

Add tests for:

- ordinary Yuno replies do not receive buttons by default
- explicit panels can render a small button set
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

- panel or targeted action chosen
- buttons added
- service paths used
- ordinary reply surface left untouched
- tests run
- checks not run and why
