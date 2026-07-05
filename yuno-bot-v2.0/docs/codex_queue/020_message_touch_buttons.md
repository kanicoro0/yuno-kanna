# 020: Message touch buttons

## Goal

Add a small message-level button surface for Yuno replies and nearby messages.

This is the closest UI layer to v1-style operation.
Instead of asking the user to open a management command, Yuno can place a few small actions near the message that matters.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/codex_queue/017_discord_view_foundation.md`
- `docs/codex_queue/016_reaction_surface.md`
- `yuno/discord/events.py`
- `yuno/pipeline.py`
- `yuno/care/`
- `yuno/care_marks/`

## Allowed scope

- message send path
- optional View attached to selected Yuno replies
- small callbacks that call existing service methods
- tests

## Do not touch

- Speaker prompt
- CareReader prompt
- routing rules
- database schema unless absolutely necessary
- arbitrary read operations
- global slash command sync behavior

## Surface target

Buttons should be sparse.
Do not attach buttons to every message by default if it makes the channel noisy.

Possible labels:

```text
残す
あとで見る
もういい
隠す
```

The exact labels can change, but they should remain short and not look like an admin console.

The button action should be understandable from the message itself.
Avoid requiring the user to know a mark id, kind, or status enum.

## Work to do

1. Decide the first narrow condition where a Yuno reply should carry buttons.
2. Add a View only in that condition.
3. Wire buttons to existing CareMark / ReadCue service paths where possible.
4. Keep failure safe and ephemeral.
5. Avoid duplicating reaction behavior.
6. Do not create hidden long-term state just because a button was shown.

## Suggested first condition

Start with replies generated from a turn that touched or created a visible mark.

That gives a concrete reason to show:

```text
残す
閉じる
隠す
```

If the turn has no mark-related context, do not show buttons yet.

## Tests

Add tests for:

- no buttons are attached when there is no eligible mark context
- eligible mark context can render a small button set
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

- first condition chosen
- buttons added
- service paths used
- cases intentionally left without buttons
- tests run
- checks not run and why
