# 008: Message intake / Turn boundary

## Goal

Prepare the runtime for natural Discord turns before adding tool execution, CareMark, ReadCue, or log-reading features.

The current runtime sends every raw Discord message directly into `ConversationPipeline.process()`. That makes short consecutive messages behave like separate turns. This task should introduce a small boundary between:

```text
raw Discord message intake
→ stored eligible conversation message
→ turn / utterance selected for Speaker and CareReader
```

Do not make Yuno smarter in this task. Make the message-processing shape cleaner so a later task can add buffering, typing presence, and interruption handling without rewriting the whole pipeline again.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/yuno_design_principles.md`
- `docs/next_direction.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/README.md`
- `yuno/discord/events.py`
- `yuno/pipeline.py`
- `yuno/discord/routing.py`
- `yuno/conversation/repository.py`

## Why this task comes before TurnBuffer

A direct TurnBuffer in `yuno/discord/events.py` would be tempting, but the current pipeline also owns routing and database append. If buffering is added only outside the pipeline, the bot may either:

- delay storage of messages that should be kept, or
- store only the final merged message, losing the original Discord message boundary.

The next design wants `ConversationLog` to keep the stored Discord message boundary and `Turn` to be the unit Yuno reads. So first split intake from turn processing.

This task does not require storing ignored messages. Preserve the current rule: bot/self messages and ordinary non-listening channel messages are ignored. For messages that are stored, keep their individual Discord message identity even if a later turn combines several of them.

## Allowed scope

- `yuno/pipeline.py`
- `yuno/discord/events.py`
- `yuno/messages.py`
- a small new module if needed, for example `yuno/turns.py` or `yuno/discord/turns.py`
- `tests/`

## Do not touch

- Speaker persona or prompt
- CareReader prompt or JSON contract
- database schema
- MemoryMark / AttentionItem / InterestTerm schema
- ToolReader / ToolExecutor behavior
- slash command surfaces
- listening channel configuration semantics
- arbitrary file/log/shell access

Do not use `create_tree` for exploration.

## Work to do

1. Introduce an internal representation for a processed turn/utterance, separate from a raw `IncomingMessage`.
   - It may be a dataclass such as `IncomingTurn` or `PipelineTurn`.
   - It should carry at least `stream_id`, combined/current speaker content, route reason, reply mode, reply target, and source user message record id(s).
   - Keep it minimal.

2. Split `ConversationPipeline.process(message)` into smaller steps while preserving current behavior:
   - intake / route / store the eligible incoming message
   - turn processing for Speaker and CareReader
   - a compatibility path where one stored message becomes one turn

3. Preserve the existing public behavior for now:
   - direct DM still replies
   - mention still replies
   - reply-to-Yuno still replies
   - listening-only still stores and only calls CareReader when the current cheap gates say it should
   - ordinary ignored messages still do not store

4. Do not implement real buffering yet.
   - This task prepares the seam.
   - A later task will add short debounce windows, typing presence, and interruption handling.

5. Make the storage semantics explicit in code comments or tests:
   - messages selected by routing for storage remain individual conversation messages
   - ignored messages remain ignored
   - turn processing may later combine several stored user messages into one turn

6. Keep the current `PipelineResult` send/finalize flow working.
   - If new names are introduced, avoid leaking internal route/turn labels to Speaker.

## Tests to add or update

Add focused unit tests for the new seam:

- a single DM message still produces a send result
- a mention still uses `discord_reply`
- a listening-only message that does not hit gates stores but does not send
- ignored bot/self messages still do not store
- the new turn representation can be built from a single stored message without changing Speaker input

Prefer small fake services/mocks over real Discord objects.

## Important constraints

- This task is a refactor boundary, not a feature expansion.
- Do not add typing presence here.
- Do not add debounce timing here.
- Do not add CareMark or ReadCue here.
- Do not change prompts.
- If preserving current behavior requires a broader rewrite than expected, stop and report the smaller safe split instead of forcing it.

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

If the script is unavailable for some reason, run:

```bash
python -m compileall main.py yuno tests
python -m unittest discover -s tests
python -c "from yuno.app import create_bot; bot=create_bot(); print('bot ok')"
```

## Codex report

Report:

- added things
- replaced things
- remaining legacy/debug things
- next deletion candidates
- whether current single-message behavior stayed equivalent
- checks run
- checks not run and why
