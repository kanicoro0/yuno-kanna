# 013: ContextBuilder / ReferenceSelector rewrite for CareMark

## Goal

Make Speaker references flow through CareMark.

After queues 011 and 012, CareMark replaces the old separate MemoryMark / AttentionItem surfaces. This task updates the Speaker context assembly and reference selection so Speaker receives only selected CareMarks.

ReadCue is used for selection, but ReadCue itself must not be shown to Speaker.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/yuno_design_principles.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/011_schema_reset_caremark_readcue.md`
- `docs/codex_queue/012_care_reader_service_rewrite.md`
- `yuno/conversation/context.py`
- `yuno/conversation/reference_selector.py`
- CareMark / ReadCue modules

## Allowed scope

- `yuno/conversation/context.py`
- `yuno/conversation/reference_selector.py`
- CareMark / ReadCue repository methods if needed
- tests

## Do not touch

- Speaker persona or prompt unless only field wording must change from memory/attention to mark
- CareReader prompt
- Discord runtime behavior
- database schema
- command UI except minimal compile fixes
- tool execution

## Work to do

1. Replace `include_memory_ids` / `include_attention_ids` with `include_care_mark_ids` where appropriate.
2. Keep SpeakerReference thin:
   - kind should remain human-safe, such as `memory` or `attention`, based on CareMark.kind
   - content should be CareMark.text
   - no internal scores, cue terms, or route reasons
3. Rewrite ReferenceSelector to:
   - find matching ReadCue terms for the current message
   - score matching CareMarks lightly
   - fall back to small text overlap if useful
   - return at most a few CareMark ids
4. Preserve the principle that references are optional and sparse.
5. Remove direct dependencies on old InterestTerm selection.

## Tests

Add tests for:

- active memory-like CareMark can be selected
- open attention-like CareMark can be selected
- hidden / closed marks are not selected unless explicitly allowed by service semantics
- ReadCue hit can select the attached CareMark
- ReadCue text itself is not rendered in Speaker context
- reference limit is respected

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
