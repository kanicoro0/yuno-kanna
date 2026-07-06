# 029: LLM care maintenance reader

## Goal

Add the concrete reader that can generate care maintenance proposals through an LLM, using the proposal-only maintenance model from queue 026.

Queue 026 added the safe shape:

```text
CareMaintenanceService
CareMaintenanceRequest
CareMaintenanceAction
CareMaintenanceProposal
CareMaintenanceReader Protocol
```

But it intentionally did not add a real LLM reader, prompt, scheduler, or command UI.

This queue should fill only the missing reader/prompt layer.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

Keep context small. Read only these first:

- `docs/codex_queue/026_periodic_care_mark_maintenance.md`
- `yuno/care/maintenance.py`
- existing LLM client/reader patterns used by `yuno/care/reader.py` or nearby code
- relevant care maintenance tests only

Only read additional files if a failing test or direct import requires it.

## Desired behavior

Add an implementation of `CareMaintenanceReader` that:

- accepts a bounded `CareMaintenanceRequest`
- calls the configured LLM once
- asks for structured proposal actions only
- returns raw output that existing parsing/validation can sanitize
- does not apply any proposal

This task must not connect maintenance to normal message handling.

## Prompt direction

The maintenance prompt should be conservative.

It should prefer:

- keeping stable memories
- closing only clearly resolved lightweight attention
- merging only clearly similar open attention
- proposing rewrites only when wording is clearly verbose/repetitive
- leaving uncertain items alone

It should not invent facts.
It should not summarize unrelated recent conversation into new memory.
It should not output raw internal details to users.
It should not create new care marks in this queue.

## Bounded context

The reader must preserve the bounds from 026.

Do not expand context beyond the request object unless explicitly needed.
Do not fetch more messages or more marks inside the reader.
Do not inspect unrelated channels/streams.

## Output format

Use the action names supported by 026 unless the 026 model is intentionally adjusted:

```text
keep
close_attention
merge_attention
rewrite_mark_text
promote_draft_memory
hide_or_ignore_noisy_mark
```

If any action name is changed, update tests and keep parser safety.

Do not add apply behavior.

## Cost discipline

This reader is allowed to call one LLM request per maintenance proposal run.

Do not add retries unless the existing client pattern already has them.
Do not call the LLM once per mark.
Do not call the LLM from normal conversation handling.

## Do not touch

- database schema
- normal Discord message pipeline
- immediate care trigger logic
- ordinary reply View behavior
- command UI
- scheduler/daily jobs
- apply buttons
- episode summaries
- selected-message actions
- reaction target behavior

## Tests

Add or update tests for:

- reader builds one bounded LLM request from a maintenance request
- reader parses fake structured LLM output into raw proposal data accepted by 026 parser
- malformed LLM output remains safe through parser path
- no real API call in tests
- normal message handling does not run the maintenance reader

Use fake LLM/client objects in tests.

## Cost discipline for Codex

Use focused tests while iterating.
Run `python scripts/check_yuno.py` once before final report.
Do not inspect the whole repo or old PRs.

## Codex report

Report:

- where the concrete maintenance reader lives
- how many LLM calls it makes per proposal run
- what prompt/output shape was added
- how malformed output is handled
- what was intentionally left unchanged
- focused tests run
- whether full check was run once
