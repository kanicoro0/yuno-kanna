# 018: Status panel View

## Goal

Turn `/status` from a plain specification list into a small status panel with buttons.

The command should still be safe and simple.
The visible surface should feel less like a bot manual and more like checking how Yuno is currently listening.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/codex_queue/017_discord_view_foundation.md`
- `yuno/commands/status.py`
- `yuno/commands/listening.py`
- `yuno/listening/`

## Allowed scope

- `/status` rendering
- status View / buttons
- listening service calls already used by commands
- tests

## Do not touch

- Speaker prompt
- CareReader prompt
- CareMark schema
- ReadOperation
- routing rules
- global slash command sync behavior

## Surface target

The status panel should avoid a table of routing modes when a shorter surface is enough.

Prefer labels like:

```text
いまの聞こえ方
DMでは返す
呼ばれたら返す
聞き耳の場所: #channel
```

Buttons may include:

```text
この場所を聞く
この場所を外す
更新
```

Do not expose:

```text
DB由来
env由来
reply_mode
CareMark
ReadCue
```

If the source distinction is needed, phrase it without implementation words.
For example, use `最初から入っている場所` rather than `.env由来`.

## Work to do

1. Replace the current `/status` plain text with a compact panel render helper.
2. Add buttons for the current channel when used in a server text channel:
   - listen here
   - stop listening here, when removable
   - refresh
3. Keep the command ephemeral.
4. Keep permission checks for changing listen targets.
5. When a location cannot be removed because it is configured outside Discord, say so without `.env` or `DB`.
6. Add tests for status text and button label choices.

## Tests

Add tests for:

- status panel does not mention internal implementation words
- empty listening list renders naturally
- current channel actions render only when channel context is usable
- non-admin change attempt gives a short rejection
- refresh returns the updated panel text

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

## Codex report

Report:

- status text before and after
- buttons added
- permission behavior
- internal words removed from visible UI
- tests run
- checks not run and why
