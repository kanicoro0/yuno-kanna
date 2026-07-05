# 017: Discord View foundation

## Goal

Add the first small Discord View foundation for Yuno surfaces.

The goal is not to replace all slash commands at once.
The goal is to make later UI work use shared, tested button helpers instead of one-off command text.

Slash commands are entry points.
Buttons are local touch points near the thing being changed.

## Working directory

Run this task from `yuno-bot-v2.0/`.

## Read first

- `docs/yuno_design_principles.md`
- `docs/implementation_practice.md`
- `docs/codex_queue/014_command_cleanup_ci.md`
- `docs/codex_queue/016_reaction_surface.md`
- `yuno/commands/`
- `yuno/discord/events.py`

## Allowed scope

- new Discord UI helper module
- small View / Button classes
- command response helpers if needed
- tests

## Do not touch

- database schema
- Speaker prompt
- CareReader prompt
- message routing
- turn buffering
- command behavior beyond what is needed for the new helpers

## Principles

Buttons should not expose implementation names.

Avoid visible words like:

- CareMark
- ReadCue
- DB
- env
- status enum names when a natural label can be used

A button should feel like touching a nearby object, not entering an admin console.

Keep the first foundation boring:

```text
YunoView
YunoButton
safe ephemeral response helper
short timeout behavior
permission guard hook
```

No persistence should be added only for UI polish.

## Work to do

1. Add a small module for shared Discord View helpers.
2. Provide a safe way for a button callback to reply ephemeral once or edit a prior ephemeral response when possible.
3. Add a small permission helper for owner/admin-only button actions.
4. Add timeout behavior that disables buttons or fails quietly.
5. Keep labels short and Yuno-facing.
6. Add tests where possible, or isolate pure label/render helpers for tests if Discord View itself is hard to unit test.

## Tests

Add tests for:

- visible labels do not contain internal implementation words
- permission helper allows owner/admin and rejects others
- timeout or disabled state does not throw during render
- callback helpers produce bounded text

## Checks

Run from `yuno-bot-v2.0/`:

```bash
python scripts/check_yuno.py
```

## Codex report

Report:

- added helpers
- visible labels introduced
- what was intentionally left as slash command text
- tests run
- checks not run and why
