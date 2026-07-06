# 026: Periodic care mark maintenance

## Goal

Add a maintenance path for care marks so Yuno does not need to decide everything immediately during conversation.

Queue 025 made immediate CareReader calls selective. This task should continue that direction:

```text
Do not grow immediate-care triggers into a large keyword/condition tree.
Keep immediate care small.
Move richer judgment to a separate maintenance pass.
```

The maintenance pass should review existing care marks and recent conversation context, then produce a safe proposal for cleanup and consolidation.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

Keep context small. Do not inspect the whole repository.

Read only these files first:

- `docs/codex_queue/025_cost_aware_selective_care_reading.md`
- `yuno/care/service.py`
- `yuno/care_marks/models.py`
- `yuno/care_marks/service.py`
- `yuno/care_marks/repository.py`
- `yuno/conversation/repository.py`
- relevant care mark tests only

Only read additional files if a failing test or direct import requires it.

## Current problem

Care marks are created near individual messages or short merged turns.
This makes them too point-like.

Problems observed:

- open attention can accumulate unless manually closed
- similar attention marks may remain separate when wording differs
- one-off lightweight questions can remain as `open` attention
- memory/attention wording can be verbose or repetitive
- trying to solve this by adding more immediate trigger conditions would create a growing condition tree

## Desired direction

Introduce a care mark maintenance layer.

This layer is separate from immediate conversation handling.
It should be callable from tests and later from a command or scheduled task.

Initial version should be proposal-only or dry-run by default.
It should not silently rewrite/delete/close marks in normal conversation.

## Core behavior

Create a small maintenance service, for example:

```text
CareMaintenanceService
```

It should be able to inspect:

- active memory
- draft memory
- open attention
- recently closed attention if useful
- recent conversation messages for the same stream

It should return a structured proposal, not immediately apply changes.

Possible proposal actions:

```text
keep
close_attention
merge_attention
rewrite_mark_text
promote_draft_memory
hide_or_ignore_noisy_mark
```

The exact names may differ, but the result must be structured and testable.

## Safety rules

For the first implementation:

- do not auto-apply proposals during normal message handling
- do not delete marks
- do not hide sensitive/draft memory automatically
- do not rewrite stable active memory automatically
- do not close attention unless explicitly applied by a future command or test path
- preserve source references where possible
- prefer conservative proposals over aggressive cleanup

## LLM usage

This task may define the shape of an LLM maintenance request/response, but keep the first implementation narrow.

Allowed approaches:

1. Proposal model and deterministic scaffolding only
2. LLM client interface with tests using fake responses
3. A dry-run maintenance method that accepts an injected reader/client

Avoid adding a real scheduled job in this task.
Avoid running maintenance automatically during conversation.

The maintenance LLM should receive bounded context:

- limited number of care marks
- limited recent messages
- no whole repository context
- no unrelated Discord command state

## Avoid condition-tree growth

Do not add many new immediate-care keywords.
Do not make `immediate_care_decision()` more complex unless absolutely necessary.
Do not add nested if/elif cleanup logic inside `ConversationPipeline`.

The main point of this task is to keep immediate care small and move richer judgment here.

## Possible implementation shape

A compact shape is enough:

```python
@dataclass(frozen=True)
class CareMaintenanceProposal:
    stream_id: int
    actions: tuple[CareMaintenanceAction, ...]

@dataclass(frozen=True)
class CareMaintenanceAction:
    action: str
    target_public_ids: tuple[str, ...]
    proposed_text: str | None = None
    reason: str = ''
```

A service method may look like:

```python
async def propose_for_stream(stream_id: int, *, limit: int = 20) -> CareMaintenanceProposal:
    ...
```

If an LLM interface is introduced, keep it injectable and fakeable in tests.

## What not to build yet

Do not build these in 026:

- `/memories tidy` UI
- buttons to apply proposals
- daily scheduler
- automatic background task
- database schema migration unless there is no simpler alternative
- cross-stream/global memory maintenance
- episode summaries
- reaction target changes

These can be later queues.

## Future queues this should enable

This task should make it easier to add later:

- `/memories tidy` proposal UI
- apply buttons for selected maintenance actions
- daily or count-based maintenance run
- episode summaries
- better source-aware reaction placement

## Tests

Add tests for:

- maintenance proposal can be generated for a stream without mutating marks
- open attention can be proposed for close/merge when fake maintenance output says so
- active memory is not rewritten/applied automatically
- proposal output is bounded and structured
- normal message handling does not run maintenance
- immediate care trigger logic does not grow for this task
- no prompt/schema/command sync changes
- ordinary Yuno replies still do not pass `view`

If an LLM-like component is added:

- tests must use a fake client/reader
- no real API call in tests
- malformed maintenance output is handled safely

## Cost discipline for Codex

Do not repeatedly run the full check suite while iterating.

During implementation:

```bash
python -m unittest <focused tests>
```

Before final report, run the full check once:

```bash
python scripts/check_yuno.py
```

Only rerun the full check if it fails and the failure is relevant.

Do not inspect the whole repo.
Do not open old PRs.
Do not read unrelated docs.
Do not perform broad cleanup.

## Codex report

Report:

- what maintenance service/model was added
- whether it is proposal-only or applies changes
- how it avoids growing immediate trigger conditions
- how LLM usage is bounded or deferred
- what behavior was intentionally left unchanged
- whether normal message handling is unaffected
- whether ordinary replies still have no View
- focused tests run
- whether `python scripts/check_yuno.py` was run once
- checks not run and why
