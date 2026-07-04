# 009: TurnBuffer + basic typing

## Goal

Add a minimal Discord turn buffer after the intake/turn seam from queue 008.

The purpose is to make short consecutive Discord messages behave like one natural turn for Yuno, while still preserving each eligible Discord message as its own stored conversation message.

Also add basic typing presence as a small body signal while Yuno is about to respond or is generating a response.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/yuno_design_principles.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/008_intake_turn_boundary.md`
- `yuno/discord/events.py`
- `yuno/pipeline.py`
- any turn/intake module created by queue 008

## Allowed scope

- Discord event/runtime layer
- turn/intake module created by queue 008
- small tests for buffering behavior

## Do not touch

- Speaker persona or prompt
- CareReader prompt or JSON contract
- database schema
- CareMark / ReadCue work
- tool execution
- command surfaces

## Work to do

1. Add a minimal per-stream TurnBuffer.
2. Buffer only messages that are already eligible for turn processing after queue 008.
3. Preserve stored source message ids for the combined turn.
4. Use a short debounce window, preferably configurable or constant-limited.
5. Keep slash commands and non-message interactions out of the buffer.
6. Add basic typing presence while a response is likely or generation is running.
7. Keep typing conservative:
   - no typing for ignored messages
   - no fake long pauses
   - no typing loop after errors

## Suggested defaults

Start with a small default window, around 1.5 to 3 seconds.

Do not tune personality here. The point is only to prevent fragmented consecutive posts from becoming fragmented Yuno turns.

## Tests

Add tests for:

- two same-author messages in the same stream within the window become one turn
- different authors are not merged
- different streams are not merged
- reply target changes prevent merging
- ignored messages do not create typing
- current single-message behavior still works

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

## Codex report

Report:

- added things
- replaced things
- remaining legacy/debug things
- next deletion candidates
- checks run
- checks not run and why
