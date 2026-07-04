# 010: Interruption / generation state

## Goal

Add a small runtime state for what Yuno is currently doing in a stream.

Queue 009 can buffer short consecutive messages and show basic typing. This task handles the next case: a new user message arrives while Yuno is already generating, waiting, or just about to send.

Do not make this an agent loop. This is only a turn-state policy.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/yuno_design_principles.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/008_intake_turn_boundary.md`
- `docs/codex_queue/009_turnbuffer_basic_typing.md`
- `yuno/discord/events.py`
- `yuno/pipeline.py`

## Allowed scope

- Discord runtime / turn manager layer
- small state dataclasses or helpers
- tests

## Do not touch

- Speaker prompt
- CareReader prompt
- database schema
- CareMark / ReadCue work
- tool execution
- command surfaces

## Work to do

1. Track per-stream generation state.
   - idle
   - buffering
   - generating
   - sending
2. Define what happens when a new eligible message arrives during each state.
3. Keep the first policy simple:
   - if still buffering, include it if merge rules allow
   - if already generating, queue it as the next turn rather than cancelling generation
   - if already sent, process it as a later turn
4. Do not implement complex regeneration unless the current code already makes it trivial.
5. Make sure typing state stops on success, failure, and cancellation.
6. Avoid concurrent sends in the same stream.

## Tests

Add tests for:

- no two sends happen concurrently in one stream
- new message during buffering can be merged
- new message during generation becomes a later turn
- generation failure returns the stream to idle
- typing state is cleaned up after failure

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
