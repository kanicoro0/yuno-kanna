# 030: Final care naturalization pass

## Goal

Finish the current care-mark sequence by making care behavior feel natural without requiring the user to think about commands.

This queue has two small goals:

1. Reduce command-centered maintenance by adding a bounded automatic cleanup path.
2. Put care reactions on the Discord message that actually caused the care mark when possible.

This is intended to be the last queue in this sequence.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

Keep context small. Read only these first:

- `docs/codex_queue/026_periodic_care_mark_maintenance.md`
- `docs/codex_queue/027_llm_care_maintenance_reader.md`
- `docs/codex_queue/028_memories_tidy_proposal_ui.md`
- `docs/codex_queue/029_apply_selected_maintenance_proposals.md`
- `yuno/care/maintenance.py`
- `yuno/care/maintenance_reader.py`
- `yuno/commands/core.py`
- `yuno/discord/events.py`
- `yuno/discord/care_reactions.py`
- `yuno/pipeline.py`
- `yuno/turns.py`
- `yuno/conversation/repository.py`
- relevant care maintenance / care reaction / Discord boundary tests only

Only read additional files if a failing test or direct import requires it.

## Part A: low-friction automatic maintenance

The current `/memories tidy` command can show proposals and manually close selected `close_attention` proposals.

For this final pass, reduce the need to use commands.

Add a small automatic maintenance path for clearly safe cleanup.

Desired behavior:

- automatically apply clearly safe `close_attention` proposals
- keep `merge_attention`, `rewrite_mark_text`, `promote_draft_memory`, and `hide_or_ignore_noisy_mark` proposal-only unless implementation stays very small and obviously safe
- do not delete marks
- do not rewrite active memory
- do not auto-promote draft memory
- do not produce noisy public messages
- do not make `/memories tidy` the main workflow

Good triggers could be one of:

- after a care mark is created, opportunistically close clearly resolved old attention for the same stream
- after a Yuno reply completes, run maintenance only when recent care activity suggests it is useful
- another small bounded trigger that does not run on every normal message

Avoid:

- scheduler/daily jobs for now
- heavy background systems
- running maintenance on every low-signal message
- requiring button presses for obvious cleanup
- making cleanup visible unless it is useful

Use `CareMaintenanceService.apply_selected()` for `close_attention` where possible.

## Part B: source-aware care reactions

Put care reactions on the message that actually caused the care mark, not necessarily the first Discord message that started the turn.

Queue 024 made multiple messages before Yuno replies coalesce into one turn. After that, a turn can be based on several source user messages. The current reaction surface may still react to the first Discord message that entered `handle_message`, which can feel wrong.

Example:

```text
ゆの
かにころってよんで
```

If the care mark is about `かにころってよんで`, the reaction should prefer that later message, not the bare `ゆの` call.

Desired behavior:

1. React to the Discord message corresponding to the mark's `source_message_id` when available.
2. If there are multiple affected marks, pick the newest/source-relevant one consistently.
3. If the target message cannot be resolved or fetched, fall back safely to the original message.
4. Never fail the conversation because reaction placement failed.

Prefer a small resolver/helper over broad rewrites.

Possible shape:

```text
CareReactionTargetResolver
```

or a small method near `events.py` that maps persisted conversation message ids to Discord message ids and fetches the Discord message from the channel.

Keep it fakeable in tests.

## Boundaries

Do not change:

- Speaker prompt
- CareReader prompt
- immediate care trigger keyword logic from 025
- selected-message action behavior
- ordinary reply View behavior
- DB schema unless there is no existing way to resolve source Discord messages
- scheduler/daily jobs
- episode summaries
- broad command redesign

## Tests

For automatic maintenance, add or update tests for:

- safe `close_attention` can be auto-applied without command/button use
- unsupported proposals remain unapplied
- unrelated marks are not changed
- no delete happens
- maintenance is bounded and does not run on every low-signal message
- ordinary Yuno sends/replies still do not pass `view`

For reactions, add or update tests for:

- merged/coalesced turn reaction prefers the later/source care message
- bare call message does not receive the reaction when a later source message can be resolved
- fallback to original source message when the target cannot be fetched
- reaction failure remains non-fatal
- ordinary sends/replies still do not pass `view`

## Cost discipline for Codex

Use focused tests while iterating.
Run `python scripts/check_yuno.py` once before final report.
Do not inspect the whole repo or old PRs.

## Codex report

Report:

- what automatic maintenance trigger was added
- what it can apply automatically
- what remains proposal-only
- how reaction targets are resolved
- what fallback behavior exists
- what was intentionally left unchanged
- focused tests run
- whether full check was run once
