# 030: Source-aware care reaction target

## Goal

Put care reactions on the message that actually caused the care mark, not necessarily the first Discord message that started the turn.

Queue 024 made multiple messages before Yuno replies coalesce into one turn. After that, a turn can be based on several source user messages. The current reaction surface may still react to the first Discord message that entered `handle_message`, which can feel wrong.

Example:

```text
ゆの
かにころってよんで
```

If the care mark is about `かにころってよんで`, the reaction should prefer that later message, not the bare `ゆの` call.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

Keep context small. Read only these first:

- `yuno/discord/events.py`
- `yuno/discord/care_reactions.py`
- `yuno/pipeline.py`
- `yuno/turns.py`
- `yuno/conversation/repository.py`
- relevant Discord boundary / turn tests only

Only read additional files if a failing test or direct import requires it.

## Current problem

`CareReactionSurface.add_for_marks()` receives one Discord `source` message and adds the reaction there.

After turn coalescing, that source may be the first message in the group, while the care mark source is the last or more specific user message.

This creates misleading reactions on generic call messages such as:

```text
ゆの
```

## Desired behavior

When a care mark has a specific source user message, prefer reacting to the Discord message for that source.

Priority:

1. React to the Discord message corresponding to the mark's `source_message_id` when available.
2. If there are multiple affected marks, pick the newest/source-relevant one consistently.
3. If the target message cannot be resolved or fetched, fall back safely to the original message.
4. Never fail the conversation because reaction placement failed.

## Implementation direction

Prefer a small resolver/helper over broad rewrites.

Possible shape:

```text
CareReactionTargetResolver
```

or a small method near `events.py` that maps persisted conversation message ids to Discord message ids and fetches the Discord message from the channel.

Keep it fakeable in tests.

## Boundaries

Do not change:

- care mark creation logic
- immediate care trigger logic from 025
- periodic maintenance from 026
- Speaker prompt
- CareReader prompt
- DB schema unless there is no existing way to find the Discord message id
- command sync
- selected-message actions
- ordinary reply View behavior

## Tests

Add or update tests for:

- merged turn reaction prefers the later/source care message
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

- how reaction targets are resolved
- what fallback behavior exists
- what was intentionally left unchanged
- focused tests run
- whether full check was run once
