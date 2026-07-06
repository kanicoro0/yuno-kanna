# 030: Apply selected maintenance proposals

## Goal

Allow selected care maintenance proposals to be applied safely, after they have been generated and shown to the user.

This queue depends on:

- 026: proposal-only care maintenance model
- 028: `/memories tidy` proposal UI
- 029: concrete maintenance reader, if proposal generation needs a real LLM path

The key rule:

```text
Only apply explicit user-selected proposals.
Never auto-apply maintenance during normal conversation.
```

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

Keep context small. Read only these first:

- `docs/codex_queue/026_periodic_care_mark_maintenance.md`
- `docs/codex_queue/028_memories_tidy_proposal_ui.md`
- `yuno/care/maintenance.py`
- the `/memories tidy` UI implementation from 028
- `yuno/care_marks/service.py`
- relevant memories UI / maintenance tests only

Only read additional files if a failing test or direct import requires it.

## Desired behavior

From the tidy proposal UI, allow owner/admin users to apply a small set of safe actions.

Supported first actions should be conservative:

- `close_attention`
- `merge_attention`
- maybe `rewrite_mark_text` for draft memory or open attention

Avoid applying high-risk actions first.

Do not apply automatically.
Do not apply all proposals by default.
Do not apply stale proposals without revalidation.

## Revalidation before apply

Before applying a proposal action, re-read the target marks and confirm:

- target ids still exist
- target kind/status still match the action
- target text has not changed unexpectedly, if text was included in the proposal snapshot
- user still has permission
- proposal action is still safe

If revalidation fails, show a short ephemeral message and do not mutate.

## Merge semantics

For `merge_attention`:

- create or keep one resulting open attention with the proposed text
- close the merged source attention marks, or touch/update one and close the rest
- preserve source references where possible
- do not delete marks

Keep this simple and tested.
If source preservation is too unclear, defer merge apply and implement only close first.

## Rewrite semantics

For `rewrite_mark_text`:

- prefer draft memory or open attention first
- avoid rewriting active memory in the first version unless explicitly allowed by tests and UI wording
- do not rewrite sensitive/draft memory into active memory
- keep status unchanged

If rewrite support becomes too broad, defer it.

## UI

Use explicit buttons tied to proposal numbers.

Examples:

```text
1 閉じる
2 まとめる
3 短くする
更新
```

Buttons must be ephemeral and owner/admin only.

After applying an action:

- edit or refresh the panel
- show which action was applied
- disable or remove stale buttons if needed

## Do not touch

- normal conversation pipeline
- immediate care trigger logic
- Speaker prompt
- CareReader prompt
- DB schema unless unavoidable
- scheduler/daily jobs
- episode summaries
- reaction target behavior
- selected-message action behavior
- ordinary reply View behavior

## Tests

Add or update tests for:

- unauthorized users cannot apply proposals
- stale proposal apply is rejected safely
- `close_attention` closes only the selected open attention
- `merge_attention` does not delete marks and does not affect unrelated marks, if implemented
- `rewrite_mark_text` does not rewrite active memory by default, if implemented
- applying one proposal does not apply all proposals
- tidy panel refreshes or disables stale action after apply
- ordinary Yuno sends/replies still do not pass `view`

## Cost discipline for Codex

Use focused tests while iterating.
Run `python scripts/check_yuno.py` once before final report.
Do not inspect the whole repo or old PRs.

## Codex report

Report:

- which proposal actions can be applied
- which actions remain proposal-only
- how stale proposals are revalidated
- what mutation each supported action performs
- permission behavior
- focused tests run
- whether full check was run once
