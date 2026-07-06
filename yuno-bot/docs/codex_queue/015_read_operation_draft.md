# 015: ReadOperation draft

## Goal

Design and add the first thin ReadOperation abstraction for reading Discord/ConversationLog ranges on request.

This is not general tool execution. It is the read-side shape for requests like:

- this channel's recent messages
- yesterday's conversation
- open work / remaining attention-like marks
- a past topic continuation

Start with a draftable internal abstraction and a small read-only path. Do not build a full agent tool system here.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/yuno_design_principles.md`
- `docs/next_direction.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/008_intake_turn_boundary.md`
- `docs/codex_queue/013_context_reference_rewrite.md`
- `docs/codex_queue/014_command_cleanup_ci.md`
- conversation repository and CareMark modules

## Allowed scope

- new read operation models/service module
- conversation repository read helpers
- narrow command or internal service path if needed
- tests

## Do not touch

- arbitrary file/log/shell access
- OS logs
- backup/restart/delete/restore
- Speaker persona or prompt
- CareReader prompt
- database schema unless only read helper indexes are truly needed
- reaction surface

## Operation shape

Keep the abstraction small:

```text
ReadOperation
  source: current_stream | conversation_log | care_marks
  range: last_n | today | yesterday | around_date
  purpose: summarize | find_open | continue_topic
  persistence: reply_only | touch_care_marks
```

The first implementation may support only a subset, for example current stream + last N + summarize.

## Rules

1. Always limit range and result size.
2. Do not pass raw large logs to Speaker.
3. Summaries should state the range read.
4. Do not read channels the bot cannot read.
5. Do not imply user-visible range checks that are not actually implemented yet.
6. If Discord permission visibility is not ready, limit this task to ConversationLog for the current stream.

## Tests

Add tests for:

- last N current stream read is bounded
- empty range gives a safe result
- summary input does not exceed configured limits
- unsupported source/range is rejected cleanly
- raw hidden/internal data is not exposed

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

## Codex report

Report:

- added things
- replaced things
- unsupported sources/ranges intentionally left out
- remaining legacy/debug things
- next deletion candidates
- checks run
- checks not run and why
