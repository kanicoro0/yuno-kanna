# MEMORY_V3_PLAN.md

## Purpose

This document is the planning note for a future memory schema v3 for the Discord bot “ゆの / 唯乃”.

The goal of schema v3 is not to make the current category system more detailed.

The goal is to move away from storing memory as a categorized profile sheet and toward storing a small set of explicit saved memories as independent records.

The current schema v2 should remain the production format until v3 is explicitly implemented and tested.

## Current issue with schema v2

Schema v2 stores memory mainly as category buckets:

```json
{
  "schema_version": 2,
  "slots": {},
  "items": {
    "好きなもの": [],
    "作業": [],
    "話し方": []
  },
  "change_log": []
}
```

This is convenient for display and editing, but it makes the bot behave as if it already has a prepared profile form for the user.

That can distort the feeling of memory. A memory may be a thought, a preference, a project fact, an instruction, and a relation to past work at the same time. Putting it into one visible category too early can reduce it.

For v3, categories should not be the canonical storage location.

## Design direction

Schema v3 should separate three layers:

1. Saved Memory
   - Stable memories the bot should explicitly keep and use in future conversations.
   - These are user-visible and user-editable.

2. Reference History
   - Conversation history that may be searched or summarized when relevant.
   - This should not automatically become a saved memory.

3. Worklog / State
   - Temporary implementation state, deployment notes, test results, or current debugging context.
   - This should normally live outside long-term memory, for example in `WORKLOG.md`, `NOTES.md`, or ordinary chat history.

The main v3 distinction is not category type. The main distinction is whether something deserves to become an explicit saved memory.

## Canonical v3 memory record

The canonical v3 unit should be an id-based memory record:

```json
{
  "id": "m_...",
  "text": "ユーザーはゆのbotを複数サーバーで運用している",
  "status": "active",
  "created_at": "2026-06-25T00:00:00+09:00",
  "updated_at": "2026-06-25T00:00:00+09:00",
  "source": {
    "type": "conversation",
    "excerpt": "現状も複数サーバーで用いてるし、それで動作確認もしてる"
  }
}
```

The memory text is the primary object.

Labels, tags, kinds, or views may exist later, but they should be secondary metadata, not the place where memory is stored.

## Minimal schema v3 shape

A possible minimal schema:

```json
{
  "schema_version": 3,
  "slots": {
    "preferred_name": "..."
  },
  "memories": {
    "m_...": {
      "id": "m_...",
      "text": "...",
      "status": "active",
      "created_at": "...",
      "updated_at": "...",
      "source": {
        "type": "conversation",
        "excerpt": "..."
      }
    }
  },
  "change_log": []
}
```

Open questions:

- Whether `memories` should be a dict keyed by id or a list of records.
- Whether `kind` is needed at all.
- Whether `confidence` is useful, or whether it adds a false sense of precision.
- Whether links between memories are needed in the first version.

## Optional metadata

These fields may be useful, but should not be added until there is a clear need:

```json
{
  "kind": "fact | preference | instruction | project | relation",
  "importance": "stable | situational | low",
  "confidence": 0.9,
  "links": [
    {"type": "related", "target": "m_..."}
  ],
  "last_used_at": "..."
}
```

Caution:

- `kind` can become a hidden category system.
- `confidence` can look more objective than it is.
- `importance` can become another profile-ranking mechanism.
- `links` can be useful, but may make the first migration too large.

## v3 operations

The v3 operation set should eventually move away from category-based item operations.

Current v2 automatic operations:

```json
{"type":"add_item","category":"...","item":"..."}
{"type":"delete_item","category":"...","item":"..."}
{"type":"rewrite_item","category":"...","old_item":"...","new_item":"..."}
{"type":"set_slot","slot":"preferred_name","value":"..."}
{"type":"delete_slot","slot":"preferred_name"}
```

Possible v3 operations:

```json
{"type":"add_memory","text":"...","source_excerpt":"..."}
{"type":"delete_memory","memory_id":"m_..."}
{"type":"rewrite_memory","memory_id":"m_...","text":"..."}
{"type":"set_slot","slot":"preferred_name","value":"..."}
{"type":"delete_slot","slot":"preferred_name"}
```

Rules:

- The model should add only small, explicit saved memories.
- Broad summaries should not become saved memories automatically.
- Ambiguous deletion or rewriting should ask for clarification.
- Each change should remain undoable.
- The source should make it possible to inspect why the memory exists.

## UI direction

The v3 UI should not default to category shelves.

Possible command behavior:

- `/memory show`
  - Shows explicit saved memories as a flat list.
  - Does not require category headings.

- `/memory recent`
  - Shows recent memory changes.

- `/memory undo`
  - Reverts the latest safe memory change.

- `/memory search query`
  - Finds relevant saved memories.

- `/memory edit`
  - Edits by selecting/searching concrete memory records, not by choosing a category first.

A first v3 experiment may change only display behavior while keeping schema v2 internally.

## Migration strategy

Do not perform a semantic rewrite of all existing memory data.

Migration should be staged:

### Phase 0: Planning only

- Add this document.
- Add a short note to `AGENTS.md` that v3 planning is active.
- Do not change runtime behavior.

### Phase 1: Flat display experiment while staying on schema v2

- Keep schema v2.
- Add a display formatter that can show existing memory items as a flat list.
- Do not change automatic memory operations yet.

### Phase 2: v3 conversion dry run

- Add a v2-to-v3 conversion function.
- Make it possible to preview converted records without writing them back.
- Preserve v2 as the production format.

### Phase 3: v3 operations behind a flag

- Add v3 operation normalization and application.
- Keep v2 operations available until v3 is tested.
- Use an environment flag only if needed.

### Phase 4: v3 UI

- Update `/memory show`, `/memory recent`, `/memory undo`, and `/memory edit` for id-based records.
- Add search only after the basic record UI is stable.

### Phase 5: production migration

- Back up `longterm_memory.json`.
- Run dry-run migration.
- Manually inspect representative users.
- Enable v3 only after undo, display, and edit are verified.

## Non-goals for the first pass

Do not do these in the first implementation pass:

- Do not create a deep category hierarchy.
- Do not convert all memories into a personality profile.
- Do not add complex relationship graphs.
- Do not change chat history storage.
- Do not remove v2 compatibility immediately.
- Do not make hidden semantic summaries of all existing memories.

## First concrete implementation task

The safest first code task is:

> Keep schema v2, but add an alternate flat memory display formatter and expose it in `/memory show` or a temporary `/memory show_flat` command.

This tests whether label-less memory display actually feels better without risking the memory storage format.
