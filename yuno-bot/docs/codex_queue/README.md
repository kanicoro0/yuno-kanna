# Codex work queue

This directory is the low-friction queue history for the staged `yuno-bot` refactor work.

Unless a task says otherwise, run Codex tasks from the `yuno-bot/` working directory.

The goal was to make the human workload as small as possible:

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

## Queue record

The numbered files here are primarily a historical implementation record and design breadcrumb trail.
They are useful for understanding why current runtime boundaries exist, but they are not the current pending roadmap by default.

When a new task explicitly points to one of these files, treat that file as scoped instructions for that task.

## Original queue order

1. `001_review_current_structure.md`
2. `002_permission_service.md`
3. `003_scope_model.md`
4. `004_tool_registry.md`
5. `005_status_entry.md`
6. `006_attention_cue_plan.md`
7. `007_readonly_toolreader.md`
8. `008_intake_turn_boundary.md`
9. `009_turnbuffer_basic_typing.md`
10. `010_interruption_generation_state.md`
11. `011_schema_reset_caremark_readcue.md`
12. `012_care_reader_service_rewrite.md`
13. `013_context_reference_rewrite.md`
14. `014_command_cleanup_ci.md`
15. `015_read_operation_draft.md`
16. `016_reaction_surface.md`

The sequence shows how the runtime moved toward the current boundaries: permission, scope, tool definitions, status display, message intake / turn boundaries, and the CareMark / ReadCue base before broader natural-language operations.

Current runtime has already moved beyond this initial queue. For the live design, prefer:

- `docs/yuno_design_principles.md`
- `docs/next_direction.md`
- `docs/implementation_practice.md`

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