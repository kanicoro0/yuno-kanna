# 028: Memories tidy proposal UI

## Goal

Expose care mark maintenance proposals through a small Discord UI without automatically applying them.

Queue 026 introduces a proposal-oriented care mark maintenance layer. This task should make those proposals visible from Discord, while keeping application/manual mutation for a later queue.

Core rule:

```text
Show tidy proposals.
Do not apply them yet.
```

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

Keep context small. Read only these first:

- `docs/codex_queue/026_periodic_care_mark_maintenance.md`
- the maintenance service/model introduced by 026
- `yuno/commands/core.py`
- `yuno/discord/ui.py`
- relevant memories/command UI tests only

Only read additional files if a failing test or direct import requires it.

## Desired user surface

Add a small command under `/memories`, for example:

```text
/memories tidy
```

It should reply ephemerally with a compact list of maintenance proposals for the current channel/stream.

The text should be user-facing and not expose internal model names.

Example style:

```text
整理案
1. 閉じてもよさそう
   「どこにいる？」はその場で返答済みかもしれない

2. まとめられそう
   似た「あとで見るもの」が2件ある
```

## What this task should not do

Do not apply proposals yet.
Do not add buttons that mutate marks yet.
Do not schedule maintenance automatically.
Do not run maintenance during normal conversation.
Do not add daily jobs.
Do not add episode summaries.

A refresh button is allowed only if it re-runs proposal generation without mutation.

## Permissions

Follow the existing `/memories list` permission style.

- Only owner/admin should see tidy proposals.
- Unauthorized users should get the same safe denial behavior as other memories commands.
- Proposals should be ephemeral.

## User-facing wording

Avoid exposing:

- CareMark
- ReadCue
- public ids unless unavoidable
- source ids
- raw kind/status enum names
- service/class names
- LLM internals

Use plain wording such as:

```text
整理案
閉じてもよさそう
まとめられそう
短くしてもよさそう
そのままでよさそう
```

## Tests

Add or update tests for:

- `/memories tidy` is registered under the memories group
- tidy response is ephemeral
- unauthorized users cannot see proposals
- proposals are rendered in user-facing wording
- tidy command does not mutate marks
- no apply buttons are present yet, or mutation buttons are absent
- ordinary Yuno sends/replies still do not pass `view`

If 026 maintenance uses an injected/fake client, tests should use the fake path and no real API call.

## Cost discipline for Codex

Use focused tests while iterating.
Run `python scripts/check_yuno.py` once before final report.
Do not inspect the whole repo or old PRs.

## Codex report

Report:

- command name and user-facing behavior
- how proposals are rendered
- confirmation that no proposal is applied
- permission behavior
- focused tests run
- whether full check was run once
