# 011: Schema reset: CareMark / ReadCue

## Goal

Replace the parallel `memory_marks`, `attention_items`, and `interest_terms` model with the simpler CareMark / ReadCue shape.

This task is allowed to reset the development database schema because yuno-bot-v2.0 has not been meaningfully operated yet. Do not preserve old data for compatibility unless the repository has changed and the task clearly needs it.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/yuno_design_principles.md`
- `docs/implementation_practice.md`
- `yuno/infra/database.py`
- current memory / attention / interest repositories and services

## Allowed scope

- `yuno/infra/database.py`
- new `yuno/care_marks/` or equivalent small module
- new `yuno/read_cues/` or equivalent small module
- removal or replacement of old model/repository/service tests
- tests

## Do not touch

- Speaker persona or prompt
- CareReader prompt contract in this task
- Discord runtime behavior
- TurnBuffer behavior
- tool execution
- command UI unless compile requires import cleanup

## Target model

CareMark should be thin:

```text
care_marks
  id
  public_id
  stream_id
  source_message_id
  kind: memory | attention
  status
  text
  created_at
  updated_at
  last_touched_at
```

ReadCue should attach to CareMark:

```text
read_cues
  id
  care_mark_id
  term
  normalized_term
  weight
  status: active | sleeping | hidden
  created_at
  updated_at
  last_touched_at
```

CareMark is the mark. ReadCue is the index back to the mark.

Do not add face/tag/reaction fields here.

## Status guidance

Use the smallest status set that keeps the old meanings:

- memory marks need active / hidden, and optionally draft if the service still needs pending-like behavior
- attention marks need open / closed / hidden

If a single CHECK constraint is awkward, prefer a simple status string with service-level validation rather than over-designing the schema.

## Work to do

1. Update schema to create `care_marks` and `read_cues`.
2. Remove or stop creating old `memory_marks`, `attention_items`, and `interest_terms` tables in the reset schema.
3. Add thin repository/service methods for CareMark and ReadCue.
4. Add upsert behavior for ReadCue by `(care_mark_id, normalized_term)`.
5. Add tests for schema creation and basic CRUD/upsert.
6. Clean imports so the app still compiles.

## Important constraints

- This is a schema/model task only.
- Do not rewrite CareReader JSON contract here unless necessary to compile; queue 012 owns that.
- Do not rewrite ContextBuilder / ReferenceSelector here unless necessary to compile; queue 013 owns that.
- Do not add emoji logic here.

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

## Codex report

Report:

- added things
- replaced things
- old tables/models removed or still remaining
- next deletion candidates
- checks run
- checks not run and why
