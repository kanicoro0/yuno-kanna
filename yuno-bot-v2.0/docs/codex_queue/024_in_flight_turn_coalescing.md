# 024: In-flight turn coalescing

## Goal

Make multiple user messages before Yuno replies behave like one conversational turn.

The current turn buffer has a short debounce window, but once a turn starts generating, later compatible messages can become a separate response even if Yuno has not replied yet.
This task should align behavior with the intended model:

```text
If the same user sends compatible messages before Yuno sends a reply, Yuno should answer the combined turn, not answer each fragment separately.
```

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `yuno/turns.py`
- `yuno/discord/events.py`
- `yuno/pipeline.py`
- existing turn / Discord boundary tests

## Current issue

A sequence such as:

```text
ゆの
どこにいる？
```

can produce two Yuno replies if the first message leaves the debounce buffer and generation starts before the second message is folded in.

The problem is not whether the first message is a call name.
The intended rule is about messages sent before Yuno replies.

## Desired behavior

For the same stream and same user, compatible messages should be coalesced while Yuno has not sent the reply yet.

The existing short debounce can remain as a quiet-window signal, but it should not be the only boundary of a turn.

Use the existing compatibility idea where possible:

- same stream
- same author
- reply target remains compatible
- direct reply/call followed by listening-only follow-up may merge
- incompatible messages should not be merged

## Implementation direction

Prefer a small turn-manager change over broad pipeline rewrites.

A possible strategy:

1. Keep the debounce window for initial quiet time.
2. Track when a stream has a generation in flight.
3. If a compatible message arrives before the assistant reply is sent, fold it into a pending replacement turn.
4. Do not send a generated reply if a newer compatible turn superseded it.
5. Regenerate using the merged content.

Avoid infinite regeneration loops.
Add a clear generation/version check or restart limit if needed.

## Important boundaries

- Do not merge messages from different users.
- Do not merge incompatible reply targets.
- Do not merge across different streams.
- Do not drop stored user messages.
- Do not send a stale reply after a newer compatible message has been absorbed.
- Do not create duplicate assistant logs for stale replies.
- Do not change Yuno's speaking/persona prompt.
- Do not attach Views or Buttons to ordinary Yuno replies.

## Do not touch

- database schema unless absolutely unavoidable
- Speaker prompt
- CareReader prompt
- command registration / sync behavior
- selected-message action behavior
- reaction behavior
- broad UI wording cleanup

## Tests

Add or update tests for:

- two compatible messages before Yuno sends produce one assistant send
- `ゆの` followed by a content message before send is answered as one combined turn
- the old generated reply is not sent if superseded by a newer compatible turn
- messages from different users are not merged
- incompatible reply targets are not merged
- stored user messages are still preserved
- assistant log is written only for the sent reply
- ordinary sends/replies still do not pass `view`

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

## Codex report

Report:

- how in-flight messages are detected
- how stale generated replies are prevented from sending
- what compatibility rules are used
- what was intentionally not changed
- tests run
- checks not run and why
