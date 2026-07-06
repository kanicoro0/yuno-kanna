# 023: Command surface wording and choices

## Goal

Make the current slash-command surface easier to understand from Discord.

Queue 017-022 added the main UI surfaces, but some commands still ask for internal-looking values or return implementation-oriented wording.
This task should clean those command surfaces without changing the underlying behavior.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/codex_queue/022_guide_command.md`
- `yuno/commands/guide.py`
- `yuno/commands/core.py`
- `yuno/commands/listening.py`
- `yuno/commands/status.py`

## Scope

Focus on user-facing command text, option descriptions, and validation messages.

Allowed:

- `/guide` wording updates
- slash command descriptions / parameter descriptions / choices where supported
- `/memories list` option help and invalid-input responses
- `/listening` response wording
- tests

Do not turn this into a behavior rewrite.

## Main issues to fix

### `/guide`

The guide should describe how to use Yuno, not explain missing implementation details.

Remove or rewrite wording like:

```text
ふつうの返事には、ボタンはつかないよ
```

Prefer something like:

```text
操作したい時は、コマンドか右クリックから開いてね
```

Add a compact note that `/memories list` can be narrowed, but do not make the guide a full manual.

### `/memories list`

The command currently accepts values such as:

```text
kind: memory / attention / all
status: draft / active / open / closed / hidden / visible / all
```

These values may remain internally, but Discord should guide the user better.

Add clear choices or descriptions where possible.

User-facing meanings:

```text
all = ぜんぶ
memory = 残したもの
attention = あとで見るもの
visible = いま見るもの
active = 覚えている
open = まだ開いている
closed = 閉じている
hidden = 隠している
draft = まだ置いてある
```

Invalid input responses should not dump raw enum lists as the main explanation.
Use short Japanese guidance instead.

### `/listening`

Do not expose `.env` or `DB` as the main user-facing concept.

Use wording such as:

```text
最初から入っている場所
後から追加した場所
コマンドでは外せない場所
```

Keep the actual behavior unchanged.

## Do not expose

- `CareMark`
- `ReadCue`
- `.env`
- `DB`
- source ids
- public ids unless the command explicitly requires them today
- raw kind/status enum names as the main visible explanation
- service/class names
- command sync internals

## Do not touch

- database schema
- Speaker prompt
- CareReader prompt
- ordinary Yuno reply send path
- guild-scoped command setup
- global command sync behavior
- selected-message mark reuse behavior
- turn buffering / generation timing
- broad file reorganization

## Tests

Add or update tests for:

- `/guide` uses user-facing wording and does not talk about missing buttons as a feature
- `/memories list` exposes useful option descriptions or choices
- invalid `/memories list` input returns short user-facing guidance
- `/listening` does not expose `.env` or `DB` wording in normal responses
- ordinary Yuno sends and replies still do not pass `view`

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

## Codex report

Report:

- what wording changed
- what choices/descriptions were added
- what behavior was intentionally left unchanged
- whether ordinary Yuno replies still have no View by default
- tests run
- checks not run and why
