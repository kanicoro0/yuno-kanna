# 016: Reaction surface for CareMark

## Goal

Add a small Discord reaction surface for CareMark after the core CareMark / ReadCue / reference flow is stable.

Reactions are surface. The database is the source of truth.

Do not make emoji into a rigid taxonomy. Yuno may choose a reaction loosely from the CareMark kind/text/status and the local feeling of the source message.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/yuno_design_principles.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/011_schema_reset_caremark_readcue.md`
- `docs/codex_queue/012_care_reader_service_rewrite.md`
- `docs/codex_queue/013_context_reference_rewrite.md`
- Discord event/runtime modules
- CareMark modules

## Allowed scope

- Discord reaction helper/surface module
- CareMark service integration point after successful mark creation/touch
- tests

## Do not touch

- CareMark schema unless a very small optional reaction metadata field is clearly needed
- Speaker prompt
- CareReader prompt
- TurnBuffer behavior
- ReadOperation
- tool execution

## Principles

```text
CareMark = mark body
ReadCue = index
reaction = Yuno's surface gesture
```

The reaction may disappear without deleting the CareMark.
The CareMark may exist without a reaction.

Keep free reactions conceptually separate from CareMark reactions. Do not try to interpret every Yuno reaction as structured memory.

## Work to do

1. Add a small reaction picker from CareMark kind/text/status and the source message when available.
2. Add reactions only when a source Discord message is available and the bot can react.
3. Failure to react must not fail CareMark creation.
4. Keep reaction choice loose, fitting, and non-authoritative rather than a fixed category table.
5. Add tests for picker behavior and failure isolation.

## Tests

Add tests for:

- visible CareMark can receive a fitting Yuno-like reaction when appropriate
- hidden/closed marks do not create new visible reactions unless explicitly intended
- reaction picker is loose and not a hard taxonomy
- reaction failure is logged or ignored without rolling back DB work

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
