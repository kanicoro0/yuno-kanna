# Codex work queue

This directory is the low-friction queue for Codex work on `yuno-bot-v2.0`.

Unless a task says otherwise, run Codex tasks from the `yuno-bot-v2.0/` working directory.

The goal is to make the human workload as small as possible:

1. Pick one numbered request.
2. Paste that request into Codex.
3. Let Codex implement it in a small branch or PR.
4. Run the fixed checks.
5. Review the PR using the template.
6. Decide: merge, ask for fixes, or stop.

## Always read first

Every Codex task should start by reading:

- `docs/yuno_design_principles.md`
- `docs/next_direction.md`
- `docs/implementation_practice.md`
- the selected file in this directory

## Queue order

1. `001_review_current_structure.md`
2. `002_permission_service.md`
3. `003_scope_model.md`
4. `004_tool_registry.md`
5. `005_status_entry.md`
6. `006_attention_cue_plan.md`
7. `007_readonly_toolreader.md`
8. `008_intake_turn_boundary.md`

Do not skip directly to tool execution. The queue intentionally builds boundaries first: permission, scope, tool definitions, status display, then message intake / turn boundaries before natural-language operations.

## Default rule

If a task would change normal conversation behavior, Speaker persona, CareReader prompt, database schema, or listening behavior, stop and explain why before editing.

## Required Codex report

Every Codex result should report:

- added things
- replaced things
- remaining legacy/debug things
- next deletion candidates
- checks run
- checks not run and why
