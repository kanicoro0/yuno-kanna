from copy import deepcopy
from datetime import datetime
import json
import re
import uuid

import discord

from config import MAX_MEMORY_CHANGE_LOG


longterm_memory = {}
memory_lock = None
longterm_memory_file = None
write_json_async = None
save_to_git_async = None


def configure(*, memory_store, lock, file_path, write_json, save_to_git):
    global longterm_memory, memory_lock, longterm_memory_file
    global write_json_async, save_to_git_async
    longterm_memory = memory_store
    memory_lock = lock
    longterm_memory_file = file_path
    write_json_async = write_json
    save_to_git_async = save_to_git


MEMORY_SCHEMA_VERSION = 2
MEMORY_V3_SCHEMA_VERSION = 3

MEMORY_SLOT_NAMES = ("preferred_name",)

MEMORY_SLOT_LABELS = {
    "preferred_name": "呼び名",
}

MEMORY_CATEGORY_ORDER = (
    "覚え書き",
    "好きなもの",
    "傾向",
    "作業",
    "創作",
    "好み",
    "話し方",
    "つながり",
    "避けたいこと",
    "その他",
)

MEMORY_CATEGORY_ALIASES = {
    "notes": "覚え書き",
    "note": "覚え書き",
    "memo": "覚え書き",
    "other_memo": "覚え書き",
    "gag_reflection": "覚え書き",
    "joke": "覚え書き",
    "humor": "覚え書き",
    "likes": "好きなもの",
    "interest": "好きなもの",
    "interests": "好きなもの",
    "traits": "傾向",
    "tendency": "傾向",
    "personality": "傾向",
    "projects": "作業",
    "work": "作業",
    "task": "作業",
    "tasks": "作業",
    "tools": "作業",
    "tool": "作業",
    "codex": "作業",
    "vscode": "作業",
    "github": "作業",
    "creative": "創作",
    "creation": "創作",
    "creation_journey": "創作",
    "art": "創作",
    "illustration": "創作",
    "book": "創作",
    "character": "創作",
    "preferences": "好み",
    "preference": "好み",
    "speech": "話し方",
    "conversation": "話し方",
    "tone": "話し方",
    "style": "話し方",
    "voice": "話し方",
    "special_call": "話し方",
    "connection": "つながり",
    "relationship": "つながり",
    "relations": "つながり",
    "avoid_topics": "避けたいこと",
    "avoid": "避けたいこと",
    "ng": "避けたいこと",
    "other": "その他",
    "misc": "その他",
    # 以前UIに出していた日本語名も、新しい10カテゴリへ畳み込む。
    "道具": "作業",
    "声": "話し方",
    "冗談の振り返り": "覚え書き",
    "創作の歩み": "創作",
    "興味": "好きなもの",
}

MEMORY_CATEGORY_GUIDANCE = (
    "道具や開発環境は『作業』、声や呼び方や会話の調子は『話し方』、"
    "冗談の振り返りは原則『覚え書き』を選ぶ。"
    "意味を決められない場合だけ『その他』を選ぶ。"
)

MEMORY_ITEM_PAGE_SIZE = 20

MEMORY_ITEM_BULLET_RE = re.compile(
    r"^\s*(?:[-–—*•・･‣⁃◦○●◎◇◆□■※]|[0-9０-９]+[.)．、]|[①-⑳])\s*"
)


def split_memory_item_text(value, *, max_length=200):
    """記憶itemを、表示可能な1行単位へ機械的に分割する。"""
    if value is None:
        return []
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)

    text = value.replace("\r\n", "\n").replace("\r", "\n")
    parts = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        line = MEMORY_ITEM_BULLET_RE.sub("", line).strip()
        if not line:
            continue
        line = re.sub(r"[ \t]+", " ", line)
        if not line:
            continue
        parts.append(line[:max_length])
    return parts


def normalize_extra_entries(extra):
    """旧JSONの extra.secret を移行するためだけの互換処理。"""
    if not isinstance(extra, dict):
        return {}

    result = {
        key: value
        for key, value in extra.items()
        if key != "secret"
    }
    legacy_secret = extra.get("secret")
    if not isinstance(legacy_secret, dict):
        if "secret" in extra:
            result["secret"] = legacy_secret
        return result

    for key, value in legacy_secret.items():
        if key not in result:
            result[key] = value
            continue
        if result[key] == value:
            continue
        fallback_key = f"secret_{key}"
        suffix = 2
        while fallback_key in result and result[fallback_key] != value:
            fallback_key = f"secret_{key}_{suffix}"
            suffix += 1
        result[fallback_key] = value
    return result

def _memory_category_source(category):
    requested = str(category or "").strip()
    while requested:
        lowered = requested.casefold()
        prefix = next(
            (
                candidate
                for candidate in ("items.", "extra.", "secret.")
                if lowered.startswith(candidate)
            ),
            None,
        )
        if not prefix:
            break
        requested = requested[len(prefix):].strip()
    if (
        not requested
        or len(requested) > 50
        or requested.casefold() in MEMORY_SLOT_NAMES
        or any(character in requested for character in ("\n", "\r", "\t"))
    ):
        return None
    return requested

def canonicalize_memory_category(category):
    """新規保存と旧カテゴリ読込を、日本語canonicalへ集約する。"""
    requested = _memory_category_source(category)
    if not requested:
        return None
    if requested in MEMORY_CATEGORY_ORDER:
        return requested
    return MEMORY_CATEGORY_ALIASES.get(requested.casefold(), "その他")

def canonicalize_memory_item(category, item):
    """未知カテゴリは「その他」へ寄せ、元キーだけ本文に残す。"""
    canonical = canonicalize_memory_category(category)
    if not canonical or not isinstance(item, str):
        return canonical, item
    item_parts = split_memory_item_text(item)
    item = item_parts[0] if item_parts else ""
    if not item:
        return canonical, item
    source = _memory_category_source(category)
    is_unknown = (
        canonical == "その他"
        and source != "その他"
        and source.casefold() not in MEMORY_CATEGORY_ALIASES
    )
    if is_unknown:
        is_legacy_secret = (
            source.casefold() == "secret"
            or source.casefold().startswith("secret_")
        )
        source_label = "旧形式" if is_legacy_secret else source
        if is_legacy_secret:
            internal_prefix = f"{source}について: "
            if item.startswith(internal_prefix):
                item = item[len(internal_prefix):]
        provenance = f"{source_label}について: "
        if not item.startswith(provenance):
            item = provenance + item
    return canonical, item[:200]

def memory_category_label(category):
    return canonicalize_memory_category(category) or "その他"

def memory_slot_label(slot):
    return MEMORY_SLOT_LABELS.get(str(slot), str(slot))

def ordered_memory_categories(entry):
    return list(MEMORY_CATEGORY_ORDER)

def normalize_item_list(values):
    if values is None:
        return []
    normalized = []
    seen = set()
    source = values if isinstance(values, list) else [values]
    for value in source:
        for item in split_memory_item_text(value):
            if item in seen:
                continue
            seen.add(item)
            normalized.append(item)
            if len(normalized) >= 50:
                return normalized
    return normalized

def normalize_legacy_item_list(values):
    """旧データも、複数行や箇条書きを1 item単位へ機械的に分割する。"""
    return normalize_item_list(values)

def merge_canonical_memory_items(items, raw_category, values):
    category = canonicalize_memory_category(raw_category)
    if not category:
        return
    canonical_values = []
    for value in normalize_legacy_item_list(values):
        _, canonical_item = canonicalize_memory_item(raw_category, value)
        if canonical_item:
            canonical_values.append(canonical_item)
    if canonical_values:
        items[category] = normalize_item_list(
            items.get(category, []) + canonical_values
        )

def empty_memory_entry():
    return {
        "schema_version": MEMORY_SCHEMA_VERSION,
        "slots": {},
        "items": {},
        "change_log": [],
    }


MEMORY_V3_COLLECTION_CATEGORY_DEFAULTS = {
    "memories": "覚え書き",
    "keywords": "好きなもの",
    "interaction_preferences": "好み",
}


def memory_root_is_v3():
    return (
        isinstance(longterm_memory, dict)
        and longterm_memory.get("schema_version") == MEMORY_V3_SCHEMA_VERSION
        and isinstance(longterm_memory.get("users"), dict)
    )


def memory_user_store():
    if memory_root_is_v3():
        return longterm_memory["users"]
    return longterm_memory


def memory_writes_supported():
    """v3 rootは dry_run が外れてから書き込み可能にする。"""
    if memory_root_is_v3():
        return longterm_memory.get("dry_run") is not True
    return True


def v3_memory_entry_to_v2_entry(entry):
    """v3の保存形を、既存UI/プロンプトが読めるv2 viewへ変換する。"""
    normalized = empty_memory_entry()
    if not isinstance(entry, dict):
        return normalized

    slots = entry.get("slots")
    if isinstance(slots, dict):
        for slot in MEMORY_SLOT_NAMES:
            value = slots.get(slot)
            if isinstance(value, str) and value.strip():
                normalized["slots"][slot] = value.strip()[:100]

    for collection, fallback_category in MEMORY_V3_COLLECTION_CATEGORY_DEFAULTS.items():
        records = entry.get(collection)
        if not isinstance(records, dict):
            continue
        for record in records.values():
            if not isinstance(record, dict):
                continue
            if record.get("status", "active") != "active":
                continue
            text_value = record.get("text")
            if not isinstance(text_value, str) or not text_value.strip():
                continue
            source_category = record.get("source_category") or fallback_category
            merge_canonical_memory_items(
                normalized["items"],
                source_category,
                text_value,
            )

    change_log = entry.get("change_log")
    if isinstance(change_log, list):
        normalized["change_log"] = [
            change for change in change_log[-MAX_MEMORY_CHANGE_LOG:]
            if isinstance(change, dict)
        ]
    if isinstance(entry.get("updated"), str):
        normalized["updated"] = entry["updated"]
    return normalized


def migrate_memory_entry(entry):
    if not isinstance(entry, dict):
        return empty_memory_entry(), True

    if entry.get("schema_version") == MEMORY_SCHEMA_VERSION:
        normalized = empty_memory_entry()
        slots = entry.get("slots")
        if isinstance(slots, dict):
            preferred_name = slots.get("preferred_name")
            if isinstance(preferred_name, str) and preferred_name.strip():
                normalized["slots"]["preferred_name"] = preferred_name.strip()[:100]

        items = entry.get("items")
        if isinstance(items, dict):
            for raw_category, values in items.items():
                merge_canonical_memory_items(
                    normalized["items"],
                    raw_category,
                    values,
                )

        change_log = entry.get("change_log")
        if isinstance(change_log, list):
            normalized["change_log"] = [
                change for change in change_log[-MAX_MEMORY_CHANGE_LOG:]
                if isinstance(change, dict)
            ]
        if isinstance(entry.get("updated"), str):
            normalized["updated"] = entry["updated"]
        return normalized, normalized != entry

    migrated = empty_memory_entry()
    preferred_name = entry.get("preferred_name")
    if isinstance(preferred_name, str) and preferred_name.strip():
        migrated["slots"]["preferred_name"] = preferred_name.strip()[:100]

    note = entry.get("note")
    merge_canonical_memory_items(migrated["items"], "notes", note)

    for category in ("likes", "traits"):
        merge_canonical_memory_items(
            migrated["items"],
            category,
            entry.get(category, []),
        )

    for raw_category, value in normalize_extra_entries(entry.get("extra", {})).items():
        merge_canonical_memory_items(migrated["items"], raw_category, value)

    if isinstance(entry.get("updated"), str):
        migrated["updated"] = entry["updated"]
    return migrated, True

def ensure_memory_entry(user_id):
    user_id = str(user_id)
    store = memory_user_store()
    raw_entry = store.get(user_id)

    if memory_root_is_v3():
        # v3 rootでは、この段階では保存形を壊さない。
        # 既存の表示・プロンプト処理に渡すため、v2互換viewだけ返す。
        return v3_memory_entry_to_v2_entry(raw_entry)

    entry, changed = migrate_memory_entry(raw_entry)
    if changed or user_id not in store:
        store[user_id] = entry
    return entry

def memory_has_content(entry):
    if isinstance(entry, dict) and entry.get("schema_version") == MEMORY_V3_SCHEMA_VERSION:
        entry = v3_memory_entry_to_v2_entry(entry)
    return bool(
        isinstance(entry, dict)
        and (entry.get("slots") or entry.get("items"))
    )

def format_memory_for_display(entry):
    if not isinstance(entry, dict):
        return []
    lines = []
    slots = entry.get("slots")
    if isinstance(slots, dict):
        for slot in MEMORY_SLOT_NAMES:
            value = slots.get(slot)
            if value:
                lines.append(f"・{memory_slot_label(slot)}: {value}")
    items = entry.get("items")
    if isinstance(items, dict):
        for category in ordered_memory_categories(entry):
            values = items.get(category, [])
            normalized_values = normalize_item_list(values)
            if normalized_values:
                lines.append(f"・{memory_category_label(category)}")
                lines.extend(f"  - {value}" for value in normalized_values)
    return lines


def format_memory_flat_for_display(entry):
    """schema v2のまま、カテゴリ見出しを出さずに記憶を表示する実験用formatter。"""
    if not isinstance(entry, dict):
        return []

    lines = []
    seen_items = set()
    slots = entry.get("slots")
    if isinstance(slots, dict):
        for slot in MEMORY_SLOT_NAMES:
            value = slots.get(slot)
            if value:
                lines.append(f"・{memory_slot_label(slot)}: {value}")

    items = entry.get("items")
    if isinstance(items, dict):
        for category in ordered_memory_categories(entry):
            for value in normalize_item_list(items.get(category, [])):
                if value in seen_items:
                    continue
                seen_items.add(value)
                lines.append(f"・{value}")

        # canonical外のカテゴリが残っていても、表示実験では落とさず末尾に出す。
        for category, values in items.items():
            if category in MEMORY_CATEGORY_ORDER:
                continue
            for value in normalize_item_list(values):
                if value in seen_items:
                    continue
                seen_items.add(value)
                lines.append(f"・{value}")
    return lines

def normalize_auto_memory_operations(operations):
    if not isinstance(operations, list):
        return [], ["memory_operations がリストではない"]

    allowed_types = {
        "add_item",
        "delete_item",
        "rewrite_item",
        "set_slot",
        "delete_slot",
    }
    normalized = []
    errors = []
    seen = set()
    for index, operation in enumerate(operations[:10]):
        label = f"operation {index + 1}"
        if not isinstance(operation, dict):
            errors.append(f"{label}: オブジェクトではない")
            continue
        operation_type = str(operation.get("type", "")).strip()
        if operation_type not in allowed_types:
            errors.append(f"{label}: 自動記憶では {operation_type!r} は使用できない")
            continue

        if operation_type == "set_slot":
            slot = str(operation.get("slot", "")).strip().lower()
            value = operation.get("value")
            if slot not in MEMORY_SLOT_NAMES:
                errors.append(f"{label}: slot が使用できない")
                continue
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > 100:
                errors.append(f"{label}: slot の値は1〜100文字にする")
                continue
            key = ("slot", slot)
            if key in seen:
                errors.append(f"{label}: 同じslotを複数回変更できない")
                continue
            seen.add(key)
            normalized.append({
                "type": "set_slot",
                "slot": slot,
                "value": value.strip(),
            })
            continue

        if operation_type == "delete_slot":
            slot = str(operation.get("slot", "")).strip().lower()
            if slot not in MEMORY_SLOT_NAMES:
                errors.append(f"{label}: slot が使用できない")
                continue
            key = ("slot", slot)
            if key in seen:
                errors.append(f"{label}: 同じslotを複数回変更できない")
                continue
            seen.add(key)
            normalized.append({
                "type": "delete_slot",
                "slot": slot,
            })
            continue

        raw_category = operation.get("category")
        category = canonicalize_memory_category(raw_category)
        if not category:
            errors.append(f"{label}: category が使用できない")
            continue
        key = ("category", category)

        if operation_type == "add_item":
            item = operation.get("item")
            item_parts = split_memory_item_text(item)
            if not item_parts:
                errors.append(f"{label}: item が空")
                continue
            if len(item_parts) > 5:
                errors.append(f"{label}: 一度に追加するitemが多すぎる")
                continue
            for item_part in item_parts:
                normalized.append({
                    "type": "add_item",
                    "category": category,
                    "item": item_part,
                })
            continue

        if operation_type == "delete_item":
            item = operation.get("item")
            item_parts = split_memory_item_text(item)
            if len(item_parts) != 1:
                errors.append(f"{label}: delete_itemのitemは1件だけにする")
                continue
            normalized.append({
                "type": "delete_item",
                "category": category,
                "item": item_parts[0],
            })
            continue

        if operation_type == "rewrite_item":
            old_item = operation.get("old_item")
            new_item = operation.get("new_item")
            old_parts = split_memory_item_text(old_item)
            new_parts = split_memory_item_text(new_item)
            if len(old_parts) != 1 or len(new_parts) != 1:
                errors.append(
                    f"{label}: rewrite_itemのold_item/new_itemは1件だけにする"
                )
                continue
            if key in seen:
                errors.append(f"{label}: 同じcategoryを複数回書き換えできない")
                continue
            seen.add(key)
            normalized.append({
                "type": "rewrite_item",
                "category": category,
                "old_item": old_parts[0],
                "new_item": new_parts[0],
            })
            continue

    if not normalized and not errors:
        errors.append("memory_operations が空")
    return normalized, errors

def append_memory_change(entry, *, source, summary, changes):
    if not changes:
        return None
    change = {
        "id": uuid.uuid4().hex[:12],
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "summary": str(summary or "記憶を変更")[:300],
        "changes": deepcopy(changes),
        "undone": False,
    }
    entry.setdefault("change_log", []).append(change)
    entry["change_log"] = entry["change_log"][-MAX_MEMORY_CHANGE_LOG:]
    entry["updated"] = change["timestamp"]
    return change

async def persist_memory_entry(entry, commit_message):
    if memory_lock is None or write_json_async is None:
        raise RuntimeError("memory_model is not configured")
    if not memory_writes_supported():
        raise RuntimeError("memory store is read-only while v3 dry_run is true")
    await write_json_async(longterm_memory_file, longterm_memory)
    if save_to_git_async:
        await save_to_git_async(commit_message)

def _remove_item(values, item):
    removed = False
    result = []
    for value in values:
        if not removed and value == item:
            removed = True
            continue
        result.append(value)
    return result, removed

def _replace_item(values, old_item, new_item):
    replaced = False
    result = []
    for value in values:
        if not replaced and value == old_item:
            result.append(new_item)
            replaced = True
        else:
            result.append(value)
    return normalize_item_list(result), replaced

def _v3_empty_user_entry():
    return {
        "schema_version": MEMORY_V3_SCHEMA_VERSION,
        "slots": {},
        "memories": {},
        "keywords": {},
        "interaction_preferences": {},
        "change_log": [],
    }


def _v3_raw_user_entry(user_id):
    store = memory_user_store()
    user_id = str(user_id)
    entry = store.get(user_id)
    if not isinstance(entry, dict):
        entry = _v3_empty_user_entry()
        store[user_id] = entry
    entry.setdefault("schema_version", MEMORY_V3_SCHEMA_VERSION)
    entry.setdefault("slots", {})
    entry.setdefault("memories", {})
    entry.setdefault("keywords", {})
    entry.setdefault("interaction_preferences", {})
    entry.setdefault("change_log", [])
    return entry


def _v3_item_collection(category, item):
    if category == "好きなもの" and isinstance(item, str) and len(item) <= 12:
        return "keywords", "k"
    if category in {"傾向", "好み", "話し方", "避けたいこと"}:
        return "interaction_preferences", "h"
    return "memories", "m"


def _v3_next_record_id(records, prefix):
    max_index = 0
    for record_id in records.keys():
        if not isinstance(record_id, str) or not record_id.startswith(prefix + "_"):
            continue
        try:
            max_index = max(max_index, int(record_id.split("_", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}_{max_index + 1:03d}"


def _v3_record_category(record, fallback):
    return canonicalize_memory_category(record.get("source_category") or fallback) or fallback


def _v3_active_records(entry):
    for collection, fallback_category in MEMORY_V3_COLLECTION_CATEGORY_DEFAULTS.items():
        records = entry.get(collection, {})
        if not isinstance(records, dict):
            continue
        for record_id, record in records.items():
            if not isinstance(record, dict):
                continue
            if record.get("status", "active") != "active":
                continue
            yield collection, fallback_category, record_id, record


def _v3_all_records(entry):
    for collection, fallback_category in MEMORY_V3_COLLECTION_CATEGORY_DEFAULTS.items():
        records = entry.get(collection, {})
        if not isinstance(records, dict):
            continue
        for record_id, record in records.items():
            if isinstance(record, dict):
                yield collection, fallback_category, record_id, record


def format_memory_records_for_display(
    user_id,
    *,
    status="active",
    collection="all",
    page=1,
    page_size=10,
):
    """v3 record実体を読み取り専用で表示する。保存データは変更しない。"""
    status = str(status or "active").strip().lower()
    collection = str(collection or "all").strip().lower()
    if status not in {"active", "deleted", "all"}:
        return ["status は active / deleted / all から選んでね"]
    if collection not in {"all", *MEMORY_V3_COLLECTION_CATEGORY_DEFAULTS.keys()}:
        return [
            "collection は all / memories / keywords / "
            "interaction_preferences から選んでね"
        ]

    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)
    page_size = max(1, min(int(page_size), 20))

    if not memory_root_is_v3():
        return ["🧾 v3 records 表示は、schema_version: 3 の記憶で使えるよ"]

    entry = memory_user_store().get(str(user_id))
    if not isinstance(entry, dict):
        return ["🧾 記憶records\nまだrecordはないみたい"]

    rows = []
    for found_collection, fallback, record_id, record in _v3_all_records(entry):
        if collection != "all" and found_collection != collection:
            continue
        record_status = str(record.get("status", "active")).strip() or "active"
        if status != "all" and record_status != status:
            continue
        text = record.get("text")
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        rows.append({
            "collection": found_collection,
            "record_id": record.get("id") if isinstance(record.get("id"), str) else record_id,
            "status": record_status,
            "source_category": record.get("source_category") or fallback,
            "text": text.strip(),
        })

    collection_order = {
        name: index
        for index, name in enumerate(MEMORY_V3_COLLECTION_CATEGORY_DEFAULTS)
    }
    rows.sort(key=lambda row: (
        collection_order.get(row["collection"], 999),
        row["record_id"],
    ))

    total = len(rows)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]

    lines = [
        "🧾 記憶records",
        f"status: {status} / collection: {collection} / page: {page}/{total_pages}",
        f"records: {total}",
    ]
    if not page_rows:
        lines.append("該当するrecordはないみたい")
        return lines

    for row in page_rows:
        text = discord.utils.escape_mentions(row["text"])
        if len(text) > 140:
            text = text[:137] + "..."
        lines.extend([
            "",
            (
                f"[{row['record_id']}] {row['collection']} / "
                f"{row['status']} / {row['source_category']}"
            ),
            text or "（textなし）",
        ])
    return lines


def _v3_find_record_by_id(entry, record_id, collection=None):
    if not isinstance(record_id, str) or not record_id.strip():
        return None, None, None, None

    if collection in MEMORY_V3_COLLECTION_CATEGORY_DEFAULTS:
        records = entry.get(collection, {})
        if isinstance(records, dict):
            record = records.get(record_id)
            if isinstance(record, dict):
                return (
                    collection,
                    MEMORY_V3_COLLECTION_CATEGORY_DEFAULTS[collection],
                    record_id,
                    record,
                )

    for found_collection, fallback, found_id, record in _v3_all_records(entry):
        if found_id == record_id:
            return found_collection, fallback, found_id, record
    return None, None, None, None


def _v3_find_record_any(
    entry,
    category,
    item,
    *,
    status=None,
    record_id=None,
    collection=None,
):
    category = canonicalize_memory_category(category)
    if not category:
        return None, None, None

    if record_id:
        found_collection, fallback, found_id, record = _v3_find_record_by_id(
            entry,
            record_id,
            collection,
        )
        if record is not None:
            if (
                _v3_record_category(record, fallback) == category
                and record.get("text") == item
                and (status is None or record.get("status", "active") == status)
            ):
                return found_collection, found_id, record

    for found_collection, fallback, found_id, record in _v3_all_records(entry):
        if status is not None and record.get("status", "active") != status:
            continue
        if _v3_record_category(record, fallback) != category:
            continue
        if record.get("text") == item:
            return found_collection, found_id, record

    return None, None, None


def _v3_restore_record(record):
    record["status"] = "active"
    record["updated_at"] = datetime.now().isoformat(timespec="seconds")


def _v3_find_record(entry, category, item):
    category = canonicalize_memory_category(category)
    for collection, fallback, record_id, record in _v3_active_records(entry):
        if _v3_record_category(record, fallback) != category:
            continue
        if record.get("text") == item:
            return collection, record_id, record
    return None, None, None


def _v3_category_items(entry, category):
    category = canonicalize_memory_category(category)
    values = []
    for _, fallback, _, record in _v3_active_records(entry):
        if _v3_record_category(record, fallback) == category:
            text_value = record.get("text")
            if isinstance(text_value, str):
                values.append(text_value)
    return normalize_item_list(values)


def _v3_add_record(entry, category, item):
    collection, prefix = _v3_item_collection(category, item)
    records = entry.setdefault(collection, {})
    record_id = _v3_next_record_id(records, prefix)
    records[record_id] = {
        "id": record_id,
        "text": item,
        "status": "active",
        "source_schema": MEMORY_V3_SCHEMA_VERSION,
        "source_category": category,
    }
    return record_id


def _v3_delete_record(record):
    record["status"] = "deleted"
    record["updated_at"] = datetime.now().isoformat(timespec="seconds")


async def apply_v3_memory_operations(user_id, operations, *, summary, source):
    if memory_lock is None:
        raise RuntimeError("memory_model is not configured")
    if not memory_writes_supported():
        return {
            "changes": [],
            "conflicts": [],
            "errors": ["v3形式の記憶は現在 dry_run のため読み取り専用"],
        }

    async with memory_lock:
        entry = _v3_raw_user_entry(user_id)
        changes = []
        conflicts = []

        for operation in operations:
            operation_type = operation["type"]

            if operation_type == "set_slot":
                slots = entry.setdefault("slots", {})
                before = slots.get(operation["slot"])
                if before == operation["value"]:
                    continue
                slots[operation["slot"]] = operation["value"]
                changes.append({**operation, "before_value": before})
                continue

            if operation_type == "delete_slot":
                slots = entry.setdefault("slots", {})
                if operation["slot"] not in slots:
                    conflicts.append(operation)
                    continue
                before = slots.pop(operation["slot"])
                changes.append({**operation, "before_value": before})
                continue

            if operation_type == "clear_category":
                category = operation["category"]
                current_items = _v3_category_items(entry, category)
                if current_items != operation.get("expected_items", []):
                    conflicts.append(operation)
                    continue
                if not current_items:
                    continue
                removed = []
                removed_targets = []
                for collection, fallback, record_id, record in list(_v3_active_records(entry)):
                    if _v3_record_category(record, fallback) == category:
                        text_value = record.get("text")
                        removed.append(text_value)
                        removed_targets.append({
                            "category": category,
                            "item": text_value,
                            "collection": collection,
                            "record_id": record_id,
                        })
                        _v3_delete_record(record)
                changes.append({
                    "type": "clear_category",
                    "category": category,
                    "old_items": normalize_item_list(removed),
                    "targets": removed_targets,
                })
                continue

            if operation_type == "delete_matching_items":
                removed_targets = []
                for target in operation.get("targets", []):
                    collection, record_id, record = _v3_find_record(
                        entry,
                        target.get("category"),
                        target.get("item"),
                    )
                    if record is None:
                        continue
                    _v3_delete_record(record)
                    removed_targets.append({
                        "category": target.get("category"),
                        "item": target.get("item"),
                        "collection": collection,
                        "record_id": record_id,
                    })
                if not removed_targets:
                    conflicts.append(operation)
                    continue
                changes.append({
                    "type": "delete_matching_items",
                    "query": operation.get("query"),
                    "category": operation.get("category"),
                    "targets": removed_targets,
                })
                continue

            category = operation["category"]

            if operation_type == "add_item":
                item = operation["item"]
                _, _, existing = _v3_find_record(entry, category, item)
                if existing is not None:
                    continue
                collection, _ = _v3_item_collection(category, item)
                record_id = _v3_add_record(entry, category, item)
                changes.append({
                    **operation,
                    "before_exists": False,
                    "collection": collection,
                    "record_id": record_id,
                })
                continue

            if operation_type == "delete_item":
                collection, record_id, record = _v3_find_record(
                    entry,
                    category,
                    operation["item"],
                )
                if record is None:
                    conflicts.append(operation)
                    continue
                _v3_delete_record(record)
                changes.append({
                    **operation,
                    "before_exists": True,
                    "collection": collection,
                    "record_id": record_id,
                })
                continue

            if operation_type == "rewrite_item":
                collection, record_id, record = _v3_find_record(
                    entry,
                    category,
                    operation["old_item"],
                )
                if record is None:
                    conflicts.append(operation)
                    continue
                record["text"] = operation["new_item"]
                record["source_category"] = category
                record["updated_at"] = datetime.now().isoformat(timespec="seconds")
                changes.append({
                    **operation,
                    "before_exists": True,
                    "collection": collection,
                    "record_id": record_id,
                })
                continue

        if changes:
            append_memory_change(
                entry,
                source=source,
                summary=summary,
                changes=changes,
            )
            await persist_memory_entry(entry, "update v3 memory")

        return {"changes": changes, "conflicts": conflicts, "errors": []}


async def apply_auto_memory_operations(user_id, operations, summary="自動記憶"):
    normalized_operations, errors = normalize_auto_memory_operations(operations)
    if not normalized_operations:
        return {"changes": [], "errors": errors}
    if memory_root_is_v3():
        result = await apply_v3_memory_operations(
            user_id,
            normalized_operations,
            summary=summary,
            source="auto",
        )
        return {
            "changes": result.get("changes", []),
            "errors": errors + result.get("errors", []),
        }

    async with memory_lock:
        entry = ensure_memory_entry(user_id)
        changes = []
        for operation in normalized_operations:
            operation_type = operation["type"]
            if operation_type == "set_slot":
                slots = entry.setdefault("slots", {})
                before = slots.get(operation["slot"])
                if before == operation["value"]:
                    continue
                slots[operation["slot"]] = operation["value"]
                changes.append({
                    **operation,
                    "before_value": before,
                })
                continue

            if operation_type == "delete_slot":
                slots = entry.setdefault("slots", {})
                if operation["slot"] not in slots:
                    continue
                before = slots.pop(operation["slot"])
                changes.append({
                    **operation,
                    "before_value": before,
                })
                continue

            category = operation["category"]
            items = entry.setdefault("items", {})
            values = normalize_item_list(items.get(category, []))

            if operation_type == "add_item":
                item = operation["item"]
                if item in values:
                    continue
                values.append(item)
                items[category] = normalize_item_list(values)
                changes.append({
                    **operation,
                    "before_exists": False,
                })
                continue

            if operation_type == "delete_item":
                item = operation["item"]
                new_values, removed = _remove_item(values, item)
                if not removed:
                    continue
                items[category] = normalize_item_list(new_values)
                changes.append({
                    **operation,
                    "before_exists": True,
                })
                continue

            if operation_type == "rewrite_item":
                old_item = operation["old_item"]
                new_item = operation["new_item"]
                new_values, replaced = _replace_item(values, old_item, new_item)
                if not replaced:
                    continue
                items[category] = new_values
                changes.append({
                    **operation,
                    "before_exists": True,
                })
                continue

        if not changes:
            return {"changes": [], "errors": errors}

        append_memory_change(
            entry,
            source="auto",
            summary=summary,
            changes=changes,
        )
        await persist_memory_entry(entry, "update memory")
        return {"changes": changes, "errors": errors}

def prepare_memory_edit_operations(raw_operations, entry):
    if not isinstance(raw_operations, list):
        return [], ["operations がリストではない"]

    normalized = []
    errors = []
    for index, operation in enumerate(raw_operations[:20]):
        label = f"operation {index + 1}"
        if not isinstance(operation, dict):
            errors.append(f"{label}: オブジェクトではない")
            continue
        operation_type = str(operation.get("type", "")).strip()

        if operation_type in {"set_slot", "delete_slot"}:
            slot = str(operation.get("slot", "")).strip().lower()
            if slot not in MEMORY_SLOT_NAMES:
                errors.append(f"{label}: slot が使用できない")
                continue
            if operation_type == "set_slot":
                value = operation.get("value")
                if not isinstance(value, str) or not value.strip() or len(value.strip()) > 100:
                    errors.append(f"{label}: slot の値は1〜100文字にする")
                    continue
                normalized.append({
                    "type": "set_slot",
                    "slot": slot,
                    "value": value.strip(),
                })
            else:
                normalized.append({
                    "type": "delete_slot",
                    "slot": slot,
                })
            continue

        if operation_type == "clear_category":
            category = canonicalize_memory_category(operation.get("category"))
            if not category:
                errors.append(f"{label}: category が使用できない")
                continue
            expected_items = normalize_item_list(
                entry.get("items", {}).get(category, [])
            )
            normalized.append({
                "type": "clear_category",
                "category": category,
                "expected_items": expected_items,
            })
            continue

        if operation_type == "delete_matching_items":
            query = str(operation.get("query", "")).strip()
            if not query or len(query) > 100:
                errors.append(f"{label}: query が使用できない")
                continue
            category_filter = canonicalize_memory_category(operation.get("category")) if operation.get("category") else None
            targets = []
            items = entry.get("items", {}) if isinstance(entry, dict) else {}
            for category in ordered_memory_categories(entry):
                if category_filter and category != category_filter:
                    continue
                for item in normalize_item_list(items.get(category, [])):
                    if query in item:
                        targets.append({"category": category, "item": item})
            if not targets:
                errors.append(f"{label}: query に一致する記憶がない")
                continue
            normalized.append({
                "type": "delete_matching_items",
                "query": query,
                "category": category_filter,
                "targets": targets[:50],
            })
            continue

        category = canonicalize_memory_category(operation.get("category"))
        if not category:
            errors.append(f"{label}: category が使用できない")
            continue

        if operation_type == "add_item":
            item = operation.get("item")
            item_parts = split_memory_item_text(item)
            if not item_parts:
                errors.append(f"{label}: item が空")
                continue
            if len(item_parts) > 20:
                errors.append(f"{label}: 一度に追加するitemが多すぎる")
                continue
            for item_part in item_parts:
                normalized.append({
                    "type": "add_item",
                    "category": category,
                    "item": item_part,
                })
            continue

        if operation_type == "delete_item":
            item = operation.get("item")
            item_parts = split_memory_item_text(item)
            if len(item_parts) != 1:
                errors.append(f"{label}: delete_itemのitemは1件だけにする")
                continue
            normalized.append({
                "type": "delete_item",
                "category": category,
                "item": item_parts[0],
            })
            continue

        if operation_type == "rewrite_item":
            old_item = operation.get("old_item")
            new_item = operation.get("new_item")
            old_parts = split_memory_item_text(old_item)
            new_parts = split_memory_item_text(new_item)
            if len(old_parts) != 1 or len(new_parts) != 1:
                errors.append(
                    f"{label}: rewrite_itemのold_item/new_itemは1件だけにする"
                )
                continue
            normalized.append({
                "type": "rewrite_item",
                "category": category,
                "old_item": old_parts[0],
                "new_item": new_parts[0],
            })
            continue

        errors.append(f"{label}: operation type が使用できない")
    return normalized, errors

async def apply_memory_edit_operations(user_id, operations, summary="手動編集"):
    operations, errors = prepare_memory_edit_operations(operations, ensure_memory_entry(user_id))
    if not operations:
        return {"changes": [], "conflicts": [], "errors": errors}
    if memory_root_is_v3():
        result = await apply_v3_memory_operations(
            user_id,
            operations,
            summary=summary,
            source="manual",
        )
        return {
            "changes": result.get("changes", []),
            "conflicts": result.get("conflicts", []),
            "errors": errors + result.get("errors", []),
        }

    async with memory_lock:
        entry = ensure_memory_entry(user_id)
        changes = []
        conflicts = []
        for operation in operations:
            operation_type = operation["type"]
            if operation_type == "set_slot":
                slots = entry.setdefault("slots", {})
                before = slots.get(operation["slot"])
                if before == operation["value"]:
                    continue
                slots[operation["slot"]] = operation["value"]
                changes.append({**operation, "before_value": before})
                continue

            if operation_type == "delete_slot":
                slots = entry.setdefault("slots", {})
                if operation["slot"] not in slots:
                    conflicts.append(operation)
                    continue
                before = slots.pop(operation["slot"])
                changes.append({**operation, "before_value": before})
                continue

            if operation_type == "clear_category":
                items = entry.setdefault("items", {})
                current_items = normalize_item_list(items.get(operation["category"], []))
                if current_items != operation["expected_items"]:
                    conflicts.append(operation)
                    continue
                if not current_items:
                    continue
                items[operation["category"]] = []
                changes.append({
                    "type": "clear_category",
                    "category": operation["category"],
                    "old_items": current_items,
                })
                continue

            if operation_type == "delete_matching_items":
                items = entry.setdefault("items", {})
                removed_targets = []
                for target in operation["targets"]:
                    category = target["category"]
                    item = target["item"]
                    current_items = normalize_item_list(items.get(category, []))
                    new_items, removed = _remove_item(current_items, item)
                    if removed:
                        items[category] = new_items
                        removed_targets.append({"category": category, "item": item})
                if not removed_targets:
                    conflicts.append(operation)
                    continue
                changes.append({
                    "type": "delete_matching_items",
                    "query": operation["query"],
                    "category": operation.get("category"),
                    "targets": removed_targets,
                })
                continue

            category = operation["category"]
            items = entry.setdefault("items", {})
            values = normalize_item_list(items.get(category, []))

            if operation_type == "add_item":
                item = operation["item"]
                if item in values:
                    continue
                values.append(item)
                items[category] = normalize_item_list(values)
                changes.append({**operation, "before_exists": False})
                continue

            if operation_type == "delete_item":
                new_values, removed = _remove_item(values, operation["item"])
                if not removed:
                    conflicts.append(operation)
                    continue
                items[category] = normalize_item_list(new_values)
                changes.append({**operation, "before_exists": True})
                continue

            if operation_type == "rewrite_item":
                new_values, replaced = _replace_item(
                    values,
                    operation["old_item"],
                    operation["new_item"],
                )
                if not replaced:
                    conflicts.append(operation)
                    continue
                items[category] = new_values
                changes.append({**operation, "before_exists": True})
                continue

        if changes:
            append_memory_change(
                entry,
                source="manual",
                summary=summary,
                changes=changes,
            )
            await persist_memory_entry(entry, "manual memory edit")
        return {"changes": changes, "conflicts": conflicts, "errors": errors}

def describe_memory_operation(operation):
    operation_type = operation.get("type")
    if operation_type == "add_item":
        return f"{memory_category_label(operation.get('category'))} に追加: {operation.get('item')}"
    if operation_type == "delete_item":
        return f"{memory_category_label(operation.get('category'))} から削除: {operation.get('item')}"
    if operation_type == "rewrite_item":
        return (
            f"{memory_category_label(operation.get('category'))} を書き換え: "
            f"{operation.get('old_item')} → {operation.get('new_item')}"
        )
    if operation_type == "set_slot":
        return f"{memory_slot_label(operation.get('slot'))} を設定: {operation.get('value')}"
    if operation_type == "delete_slot":
        return f"{memory_slot_label(operation.get('slot'))} を削除"
    if operation_type == "clear_category":
        return f"{memory_category_label(operation.get('category'))} を全削除"
    if operation_type == "delete_matching_items":
        return f"{operation.get('query')} に一致する記憶を削除"
    return "記憶を変更"

def format_recent_memory_changes(entry, limit=10):
    change_log = entry.get("change_log", []) if isinstance(entry, dict) else []
    lines = []
    for change in reversed(change_log[-limit:]):
        timestamp = str(change.get("timestamp", ""))[:19]
        source_label = "自動" if change.get("source") == "auto" else "手動"
        undone = "（取消済み）" if change.get("undone") else ""
        changes = change.get("changes", [])
        if not isinstance(changes, list):
            changes = []
        descriptions = [
            describe_memory_operation(operation)
            for operation in changes[:5]
            if isinstance(operation, dict)
        ]
        if len(changes) > 5:
            descriptions.append(f"ほか{len(changes) - 5}件")
        marker = "📝"
        types = {operation.get("type") for operation in changes if isinstance(operation, dict)}
        if types and types <= {"add_item"}:
            marker = "📌"
        elif types and types <= {"delete_item", "delete_matching_items", "clear_category", "delete_slot"}:
            marker = "🗑️"
        lines.append(
            f"{marker} {timestamp} [{source_label}] "
            + "／".join(descriptions or [str(change.get("summary", "記憶を変更"))])
            + undone
        )
    return lines

def _can_undo_change(entry, change):
    for operation in reversed(change.get("changes", [])):
        operation_type = operation.get("type")
        if operation_type == "add_item":
            category = operation["category"]
            item = operation["item"]
            if item not in normalize_item_list(entry.get("items", {}).get(category, [])):
                return False
        elif operation_type == "delete_item":
            category = operation["category"]
            item = operation["item"]
            if item in normalize_item_list(entry.get("items", {}).get(category, [])):
                return False
        elif operation_type == "rewrite_item":
            category = operation["category"]
            new_item = operation["new_item"]
            if new_item not in normalize_item_list(entry.get("items", {}).get(category, [])):
                return False
        elif operation_type == "set_slot":
            current = entry.get("slots", {}).get(operation["slot"])
            if current != operation.get("value"):
                return False
        elif operation_type == "delete_slot":
            if operation["slot"] in entry.get("slots", {}):
                return False
        elif operation_type == "clear_category":
            category = operation["category"]
            if normalize_item_list(entry.get("items", {}).get(category, [])):
                return False
        elif operation_type == "delete_matching_items":
            for target in operation.get("targets", []):
                category = target["category"]
                item = target["item"]
                if item in normalize_item_list(entry.get("items", {}).get(category, [])):
                    return False
        else:
            return False
    return True

def _undo_operation(entry, operation):
    operation_type = operation.get("type")
    if operation_type == "add_item":
        category = operation["category"]
        values = normalize_item_list(entry.setdefault("items", {}).get(category, []))
        entry["items"][category], _ = _remove_item(values, operation["item"])
        return True

    if operation_type == "delete_item":
        category = operation["category"]
        values = normalize_item_list(entry.setdefault("items", {}).get(category, []))
        item = operation["item"]
        if item not in values:
            values.append(item)
        entry["items"][category] = normalize_item_list(values)
        return True

    if operation_type == "rewrite_item":
        category = operation["category"]
        values = normalize_item_list(entry.setdefault("items", {}).get(category, []))
        entry["items"][category], replaced = _replace_item(
            values,
            operation["new_item"],
            operation["old_item"],
        )
        return replaced

    if operation_type == "set_slot":
        slots = entry.setdefault("slots", {})
        before = operation.get("before_value")
        if before is None:
            slots.pop(operation["slot"], None)
        else:
            slots[operation["slot"]] = before
        return True

    if operation_type == "delete_slot":
        before = operation.get("before_value")
        if before is not None:
            entry.setdefault("slots", {})[operation["slot"]] = before
        return True

    if operation_type == "clear_category":
        entry.setdefault("items", {})[operation["category"]] = normalize_item_list(
            operation.get("old_items", [])
        )
        return True

    if operation_type == "delete_matching_items":
        items = entry.setdefault("items", {})
        for target in operation.get("targets", []):
            category = target["category"]
            item = target["item"]
            values = normalize_item_list(items.get(category, []))
            if item not in values:
                values.append(item)
            items[category] = normalize_item_list(values)
        return True

    return False

def _v3_operation_record_kwargs(operation):
    return {
        "record_id": operation.get("record_id"),
        "collection": operation.get("collection"),
    }


def _v3_restore_deleted_item(entry, operation, category, item):
    collection, record_id, record = _v3_find_record_any(
        entry,
        category,
        item,
        status="deleted",
        **_v3_operation_record_kwargs(operation),
    )
    if record is None:
        return False
    _v3_restore_record(record)
    return True


def _v3_can_undo_change(entry, change):
    for operation in reversed(change.get("changes", [])):
        operation_type = operation.get("type")

        if operation_type == "add_item":
            _, _, record = _v3_find_record_any(
                entry,
                operation.get("category"),
                operation.get("item"),
                status="active",
                **_v3_operation_record_kwargs(operation),
            )
            if record is None:
                return False

        elif operation_type == "delete_item":
            _, _, active_record = _v3_find_record_any(
                entry,
                operation.get("category"),
                operation.get("item"),
                status="active",
            )
            if active_record is not None:
                return False
            _, _, deleted_record = _v3_find_record_any(
                entry,
                operation.get("category"),
                operation.get("item"),
                status="deleted",
                **_v3_operation_record_kwargs(operation),
            )
            if deleted_record is None:
                return False

        elif operation_type == "rewrite_item":
            _, _, new_record = _v3_find_record_any(
                entry,
                operation.get("category"),
                operation.get("new_item"),
                status="active",
                **_v3_operation_record_kwargs(operation),
            )
            if new_record is None:
                return False
            _, _, old_record = _v3_find_record_any(
                entry,
                operation.get("category"),
                operation.get("old_item"),
                status="active",
            )
            if old_record is not None and old_record is not new_record:
                return False

        elif operation_type == "set_slot":
            current = entry.get("slots", {}).get(operation.get("slot"))
            if current != operation.get("value"):
                return False

        elif operation_type == "delete_slot":
            if operation.get("slot") in entry.get("slots", {}):
                return False

        elif operation_type == "clear_category":
            category = operation.get("category")
            if _v3_category_items(entry, category):
                return False
            targets = operation.get("targets")
            if isinstance(targets, list) and targets:
                for target in targets:
                    _, _, record = _v3_find_record_any(
                        entry,
                        target.get("category", category),
                        target.get("item"),
                        status="deleted",
                        record_id=target.get("record_id"),
                        collection=target.get("collection"),
                    )
                    if record is None:
                        return False
            else:
                for item in operation.get("old_items", []):
                    _, _, record = _v3_find_record_any(
                        entry,
                        category,
                        item,
                        status="deleted",
                    )
                    if record is None:
                        return False

        elif operation_type == "delete_matching_items":
            for target in operation.get("targets", []):
                _, _, active_record = _v3_find_record_any(
                    entry,
                    target.get("category"),
                    target.get("item"),
                    status="active",
                )
                if active_record is not None:
                    return False
                _, _, deleted_record = _v3_find_record_any(
                    entry,
                    target.get("category"),
                    target.get("item"),
                    status="deleted",
                    record_id=target.get("record_id"),
                    collection=target.get("collection"),
                )
                if deleted_record is None:
                    return False

        else:
            return False

    return True


def _v3_undo_operation(entry, operation):
    operation_type = operation.get("type")

    if operation_type == "add_item":
        _, _, record = _v3_find_record_any(
            entry,
            operation.get("category"),
            operation.get("item"),
            status="active",
            **_v3_operation_record_kwargs(operation),
        )
        if record is None:
            return False
        _v3_delete_record(record)
        return True

    if operation_type == "delete_item":
        return _v3_restore_deleted_item(
            entry,
            operation,
            operation.get("category"),
            operation.get("item"),
        )

    if operation_type == "rewrite_item":
        _, _, record = _v3_find_record_any(
            entry,
            operation.get("category"),
            operation.get("new_item"),
            status="active",
            **_v3_operation_record_kwargs(operation),
        )
        if record is None:
            return False
        record["text"] = operation.get("old_item")
        record["source_category"] = operation.get("category")
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        return True

    if operation_type == "set_slot":
        slots = entry.setdefault("slots", {})
        before = operation.get("before_value")
        if before is None:
            slots.pop(operation.get("slot"), None)
        else:
            slots[operation.get("slot")] = before
        return True

    if operation_type == "delete_slot":
        before = operation.get("before_value")
        if before is not None:
            entry.setdefault("slots", {})[operation.get("slot")] = before
        return True

    if operation_type == "clear_category":
        targets = operation.get("targets")
        if isinstance(targets, list) and targets:
            for target in targets:
                if not _v3_restore_deleted_item(
                    entry,
                    target,
                    target.get("category", operation.get("category")),
                    target.get("item"),
                ):
                    return False
            return True

        for item in operation.get("old_items", []):
            fallback_operation = {"type": "delete_item"}
            if not _v3_restore_deleted_item(
                entry,
                fallback_operation,
                operation.get("category"),
                item,
            ):
                return False
        return True

    if operation_type == "delete_matching_items":
        for target in operation.get("targets", []):
            if not _v3_restore_deleted_item(
                entry,
                target,
                target.get("category"),
                target.get("item"),
            ):
                return False
        return True

    return False


async def undo_latest_memory_change(user_id, *, source=None):
    if not memory_writes_supported():
        return {"undone": False, "reason": "v3_read_only"}

    async with memory_lock:
        if memory_root_is_v3():
            entry = _v3_raw_user_entry(user_id)
        else:
            entry = ensure_memory_entry(user_id)

        change_log = entry.get("change_log", [])
        target = None
        for change in reversed(change_log):
            if change.get("undone"):
                continue
            if source and change.get("source") != source:
                continue
            target = change
            break
        if not target:
            return {"undone": False, "reason": "empty"}

        if memory_root_is_v3():
            if not _v3_can_undo_change(entry, target):
                return {"undone": False, "reason": "conflict", "change": target}
            for operation in reversed(target.get("changes", [])):
                if not _v3_undo_operation(entry, operation):
                    return {"undone": False, "reason": "unsupported", "change": target}
        else:
            if not _can_undo_change(entry, target):
                return {"undone": False, "reason": "conflict", "change": target}
            for operation in reversed(target.get("changes", [])):
                if not _undo_operation(entry, operation):
                    return {"undone": False, "reason": "unsupported", "change": target}

        target["undone"] = True
        target["undone_at"] = datetime.now().isoformat(timespec="seconds")
        entry["updated"] = target["undone_at"]
        await persist_memory_entry(entry, "undo memory change")
        return {"undone": True, "change": target}

async def undo_latest_auto_memory(user_id):
    return await undo_latest_memory_change(user_id, source="auto")

def format_auto_memory_debug_summary(result):
    changes = result.get("changes", []) if isinstance(result, dict) else []
    errors = result.get("errors", []) if isinstance(result, dict) else []
    lines = []
    if changes:
        lines.append("accepted:")
        lines.extend(f"- {describe_memory_operation(change)}" for change in changes[:10])
    if errors:
        lines.append("ignored:")
        lines.extend(f"- {error}" for error in errors[:10])
    return "\n".join(lines)
