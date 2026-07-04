# 001: Review current structure

## Goal

Review the current `yuno-bot-v2.0` structure before adding new implementation layers.

This task should produce a short map and recommendations. It should not change runtime behavior.

## Read first

- `docs/yuno_design_principles.md`
- `docs/next_direction.md`
- `docs/implementation_practice.md`
- `README.md`

## Allowed scope

- `yuno-bot-v2.0/docs/`
- optional notes under `yuno-bot-v2.0/docs/codex_queue/`

## Do not touch

- runtime Python code
- database schema
- Speaker persona or prompt
- CareReader prompt
- routing/listening behavior
- Discord command behavior

## Work to do

1. Read the main modules and make a concise map of current boundaries:
   - Discord adapter/events
   - routing
   - pipeline
   - context builder
   - Speaker
   - CareReader / CareService
   - Memory / Attention / Interest
   - infra/database
2. Identify where the next layers should live:
   - permissions
   - scope
   - tools
   - status/settings/memories/tools UI
3. List any duplicated or ambiguous concepts.
4. List next deletion or consolidation candidates.

## Output expected

Add or update a short note in `docs/` only if useful. Otherwise report findings in the Codex response.

## Checks

No runtime checks are required if no code changes were made.

If Codex changes any file, report exactly which file changed and why.
