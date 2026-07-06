# 012: CareReader / CareService rewrite for CareMark

## Goal

Rewrite the care observation path to use CareMark and ReadCue instead of separate MemoryMark, AttentionItem, and InterestTerm outputs.

Queue 011 owns the schema/model reset. This task owns the CareReader JSON contract, parsing, and CareService application logic.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/yuno_design_principles.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/011_schema_reset_caremark_readcue.md`
- `yuno/care/reader.py`
- `yuno/care/models.py`
- `yuno/care/service.py`
- CareMark / ReadCue modules from queue 011

## Allowed scope

- `yuno/care/`
- CareMark / ReadCue service methods if needed
- tests

## Do not touch

- Speaker persona or prompt
- Discord runtime behavior
- TurnBuffer behavior
- ContextBuilder / ReferenceSelector except minimal compile fixes
- command UI except minimal compile fixes
- tool execution

## New CareReader contract

Replace the old shape:

```text
memory_candidates
attention_candidates
interest_updates
```

with a thinner shape:

```text
care_mark_candidates[{kind,status,text,confidence?,sensitive?,about_other_person?}]
read_cue_updates[{care_mark_public_id?, candidate_text?, term, weight}]
touch_care_mark_ids[]
include_care_mark_ids[]
wants_to_speak
should_speak
```

Keep the final exact JSON shape small and documented in `CARE_SYSTEM_PROMPT`.

## Behavior

1. CareReader returns candidates only.
2. CareService decides create / touch / merge / ignore.
3. Memory-like CareMarks should stay sparse.
4. Attention-like CareMarks may be touched instead of duplicated.
5. ReadCue is upserted and does not go to Speaker directly.
6. Sensitive or other-person assertions should not become active memory-like marks.

## Dedupe guidance

Add simple normalization first:

- NFKC
- casefold
- compact whitespace and punctuation for matching

Avoid aggressive semantic merging. If only vaguely similar, keep it separate or ignore rather than merging incorrectly.

## Tests

Add tests for:

- CareReader parser accepts new fields
- invalid kind/status is ignored
- sensitive active memory-like candidate is downgraded or not activated
- CareService creates a CareMark candidate
- CareService touches existing similar open attention-like CareMark instead of duplicating
- ReadCue updates are upserted
- ReadCue is not included in Speaker-facing reference data

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
