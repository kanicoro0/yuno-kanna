# 006: Attention cue plan

## Goal

Plan the migration from independent `InterestTerm` to Attention-owned cue/term behavior.

This task is mostly planning. It should not drop tables or break compatibility.

## Read first

- `docs/yuno_design_principles.md`
- `docs/next_direction.md`
- `docs/implementation_practice.md`
- `docs/legacy_v2_import_plan.md`

## Allowed scope

- `docs/`
- small comments or naming notes in code only if they reduce confusion
- tests only if a pure compatibility helper is added

## Do not touch

- database schema drop/removal
- destructive migration
- CareReader prompt, unless this task is explicitly split and approved later
- Speaker prompt
- normal conversation behavior
- listening behavior
- UI behavior

## Work to do

1. Review current `InterestTerm` usage.
2. Identify the smallest path toward treating interest terms as Attention cues.
3. Propose a staged migration:
   - keep existing table for compatibility
   - hide or de-emphasize independent Interest UI
   - introduce cue vocabulary at the service/model boundary
   - later migrate data only with explicit migration task
4. Identify what should be deleted later, but do not delete it now.
5. Write a concise implementation note if useful.

## Important constraints

- Do not remove `InterestTerm` yet.
- Do not create another parallel concept.
- Do not make cues a new independent memory system.
- Cues exist to help Attention be found, not to become a separate protagonist.

## Checks

No runtime checks are required if only docs change.

If code changes, run:

```bash
python -m compileall main.py yuno tests
python -m unittest discover -s tests
python -c "from yuno.app import create_bot; bot=create_bot(); print('bot ok')"
```

## Codex report

Report:

- added things
- replaced things
- remaining legacy/debug things
- next deletion candidates
- checks run
