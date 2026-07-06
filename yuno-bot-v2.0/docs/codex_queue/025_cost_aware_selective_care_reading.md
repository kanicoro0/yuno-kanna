# 025: Cost-aware selective care reading

## Goal

Reduce unnecessary LLM usage from Yuno's care/memory processing.

The current system stores every eligible message, then Yuno may run CareReader around replies to extract memory, attention, and read cues. This can make light conversational turns expensive and can also create too many small attention marks.

This task should make immediate care reading selective.

Core rule:

```text
Always store the conversation log.
Do not always run the care/memory LLM.
Run it immediately only when a cheap trigger says the message is likely worth memory/attention processing.
```

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

Keep context small. Do not inspect the whole repository.

Read only these files first:

- `yuno/pipeline.py`
- `yuno/care/service.py`
- `yuno/care/reader.py`
- `yuno/care/models.py`
- `yuno/discord/events.py`
- relevant tests for pipeline/care/discord boundary

Only read additional files if a failing test or direct import requires it.

## Current problem

CareReader is useful, but running it too often has two costs:

1. token/API cost
2. memory quality cost

Frequent immediate reading encourages tiny, scattered care marks such as one-off questions or casual remarks. These should usually remain in the conversation log and be considered later by maintenance, not immediately turned into open attention.

## Desired behavior

Every eligible Discord message should still be stored.
Speaker replies should still work as before.
Assistant replies should still be logged after send.

But CareReader should be skipped for ordinary low-signal turns.

Use cheap deterministic triggers before calling CareReader.

Possible immediate-care triggers:

- explicit memory language
  - `覚えて`
  - `忘れないで`
  - `メモ`
  - `記憶`
  - `あとで`
  - `後で見る`
- name/call-name preference language
  - `呼んで`
  - `呼び名`
  - `名前`
- user preference language
  - `好き`
  - `嫌い`
  - `苦手`
  - `好み`
- scheduled or unresolved items
  - `予定`
  - `締切`
  - `やること`
  - `忘れそう`
- strong existing cue salience
- strong overlap with existing open attention
- manual mark actions, such as selected-message actions, should remain explicit paths and should not depend on these triggers

The exact trigger list may be adjusted, but it must be cheap and non-LLM.

## Important distinction

Do not remove care processing entirely.

This task only reduces immediate CareReader calls.
A later maintenance task can periodically review accumulated logs/marks and consolidate them with an LLM.

## Suggested implementation direction

Introduce a small trigger function or service, for example:

```text
should_run_immediate_care(turn, content, state, phase) -> CareTriggerDecision
```

Where the decision can include:

```text
run: bool
reason: str
```

Use it before calling CareReader in both relevant paths:

- pre-send care reading for listening-only turns
- post-send observation after Yuno replies

Do not call another LLM to make this decision.

## Logging

Add debug logs that make usage understandable without exposing user content unnecessarily.

Examples:

```text
care_reader skipped stream_id=... reason=low_signal
care_reader called stream_id=... reason=explicit_memory
```

Do not log full message content.

## User-facing behavior

No new user-facing command is required.

Do not change ordinary Yuno replies.
Do not add buttons to ordinary replies.
Do not expose the trigger system in `/guide`.

## Do not touch

- database schema
- Speaker prompt
- CareReader prompt unless absolutely necessary
- command registration/sync behavior
- guild-scoped commands
- selected-message actions
- right-click command behavior
- reaction target behavior
- periodic maintenance or daily jobs
- broad UI cleanup

## Tests

Add or update tests for:

- ordinary low-signal reply does not call CareReader after send
- explicit memory/call-name preference language does call CareReader
- low-signal listening-only messages do not call CareReader
- high cue salience or strong open-attention overlap can still call CareReader
- skipped CareReader creates no new care marks or reactions
- conversation logging still happens
- assistant logging still happens when Yuno replies
- manual selected-message mark actions are unaffected
- ordinary Yuno sends/replies still do not pass `view`

## Cost discipline for Codex

Keep the implementation narrow.

Do not read large unrelated files.
Do not open old PRs.
Do not inspect all docs.
Do not rewrite care mark models or command UI.
If more context is needed, read the smallest file or test that answers the question.

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

## Codex report

Report:

- where the trigger logic lives
- which turns now skip CareReader
- which triggers still call CareReader immediately
- what behavior was intentionally left unchanged
- whether ordinary replies still have no View
- tests/checks run
- checks not run and why
