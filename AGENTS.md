# AGENTS.md

## Project

This repository contains the Discord bot “ゆの / 唯乃”.

The bot is written in Python using discord.py and the OpenAI API.

## Repository layout

- `main.py`: entrypoint
- `yuno_core.py`: startup, shared state injection, JSON loading, command/event registration, setup hook, slash command sync, startup notification, common error handling
- `conversation.py`: message handling, prompt construction, AI response parsing, automatic memory operations, reaction handling
- `memory_model.py`: memory schema, category normalization, migration, memory operation validation/apply/undo, change log, recent formatting
- `memory_ui.py`: `/memory show`, `/memory recent`, `/memory undo`, `/memory edit`
- `reminders.py`: `/remind`, `/cancelremind`, `/reminders`, reminder restore on startup
- `server_memory.py`: `/servermemory show`, `/servermemory set`
- `owner_tools.py`: owner-only commands
- `general_commands.py`: `/guide`, `/status`
- `storage.py`: JSON load/save and optional Git save
- `config.py`: environment variables and constants
- `openai_client.py`: shared OpenAI client wrapper

## Runtime files

The following files are runtime state or local secrets and must not be committed to Git:

- `.env`
- `longterm_memory.json`
- `chat_history.json`
- `guild_notes.json`
- `reminders.json`
- `last_prompt.json`

Also do not commit:

- `.venv/`
- `**/.venv/`
- `__pycache__/`
- `*.pyc`
- backup files

## Current design constraints

- Keep `schema_version` at `2`.
- Do not introduce schema v3 unless explicitly requested.
- Do not reintroduce `/pendingmemory`.
- Do not reintroduce `/forget`.
- Do not add confirmation UI for automatic memory changes.
- Do not send extra system messages for each memory change.
- Do not log raw `memory_operations` to Discord.
- Do not semantically rewrite or summarize all existing memory data.
- Prefer small, reversible changes.
- Preserve existing runtime JSON behavior.
- Prefer localized patches over broad rewrites.
- Do not reorganize modules unless the task explicitly asks for it.
- Do not change behavior unrelated to the requested issue.

## Memory system

Memory uses schema v2:

```json
{
  "schema_version": 2,
  "slots": {},
  "items": {},
  "change_log": []
}
```

Canonical memory categories are Japanese:

- `覚え書き`
- `好きなもの`
- `傾向`
- `作業`
- `創作`
- `好み`
- `話し方`
- `つながり`
- `避けたいこと`
- `その他`

English or legacy category names may exist only as aliases for reading old data.

`preferred_name` belongs in `slots.preferred_name`, not in `items`.

## Automatic memory operations

Automatic memory changes should use `memory_operations v2`.

Allowed operation types:

```json
{"type":"add_item","category":"...","item":"..."}
{"type":"delete_item","category":"...","item":"..."}
{"type":"rewrite_item","category":"...","old_item":"...","new_item":"..."}
{"type":"set_slot","slot":"preferred_name","value":"..."}
{"type":"delete_slot","slot":"preferred_name"}
```

Rules:

- Clear, small memory changes may be applied immediately.
- Ambiguous or broad requests should not create operations.
- Use normal conversation to ask for clarification when needed.
- Multiple operations from one user message should become one change log entry.
- `/memory recent` should show the grouped change.
- `/memory undo` should undo the grouped change.
- Automatic changes should be reversible when possible.

## Reserved reactions

The following reactions are reserved for memory-operation results:

- `📌`: memory item added
- `🗑️`: memory item deleted
- `📝`: memory item rewritten or slot changed

These reactions must only be added by code after memory operations are successfully applied.

The AI response `reaction` field must never add `📌`, `🗑️`, or `📝`.

Recent channel-log reactions passed into prompts should exclude `📌`, `🗑️`, and `📝` so the model does not imitate system reactions.

## Memory item formatting

A memory item should be a single atomic item.

Rules:

- One item should not contain multiple bullet points.
- One item should not contain raw newline-separated lists.
- If an added item contains multiple bullet lines, split it into multiple items when safe.
- `delete_item` and `rewrite_item` should not silently split multi-line targets.
- Existing multiline items may be mechanically normalized, but do not semantically summarize them.

Example:

```text
音楽
- 哲学
- 雨音
- 青色
```

should be treated as:

```text
音楽
哲学
雨音
青色
```

## Slash command sync policy

This bot is used in multiple Discord servers.

Use global slash command sync for normal operation:

```python
await bot.tree.sync()
```

Do not use `copy_global_to(guild=...)` and `sync(guild=...)` as the normal startup path, because that can create duplicate commands in the development/personal server when global commands also exist.

`DISCORD_GUILD_ID` may be used only as a temporary cleanup target for removing stale guild commands from one server.

When cleaning stale guild commands, clear only the specific guild commands and keep global commands intact:

```python
guild = discord.Object(id=DISCORD_GUILD_ID)
bot.tree.clear_commands(guild=guild)
await bot.tree.sync(guild=guild)
await bot.tree.sync()
```

After stale guild commands are cleared, remove or comment out `DISCORD_GUILD_ID` in the VPS `.env`.

## Git save policy

`save_to_git_async()` may remain in the codebase.

Normal operation should not commit runtime JSON.

`ENABLE_GIT_SAVE` should default to off:

```python
ENABLE_GIT_SAVE = os.getenv("ENABLE_GIT_SAVE", "0") == "1"
```

Only when `.env` explicitly sets `ENABLE_GIT_SAVE=1` should runtime JSON be committed.

## Testing / verification

After Python code changes, run at least:

```bash
python -m py_compile *.py
```

When relevant, also manually test these Discord commands:

- `/status`
- `/guide`
- `/memory show`
- `/memory recent`
- `/memory undo`
- `/memory edit`
- `/remind`
- `/reminders`
- `/cancelremind`
- `/servermemory show`
- `/servermemory set`

For memory changes, verify:

- memory additions get `📌`
- memory deletions get `🗑️`
- memory rewrites or slot changes get `📝`
- normal AI reactions never use `📌`, `🗑️`, or `📝`
- `/memory show` does not display broken nested bullet lists
- `/memory undo` can revert the latest safe memory change

For slash command sync, verify:

- multiple servers can use the bot commands
- the personal/development server does not show duplicate slash commands
- global commands were not accidentally deleted when clearing stale guild commands

## Worklog policy

Do not put temporary status notes in this file.

Use `WORKLOG.md` or `NOTES.md` for:

- what was done in a specific session
- manual test results
- temporary bugs to check next
- deployment notes
- accidental mistakes such as forgotten pushes
