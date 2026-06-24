from copy import deepcopy
from datetime import datetime
import json
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
    item = item.strip()
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
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        value = value.strip()
        if not value or len(value) > 200 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
        if len(normalized) >= 50:
            break
    return normalized

def normalize_legacy_item_list(values):
    """旧データは長文を捨てず、新規入力と同じ上限へ機械的に切り詰める。"""
    if values is None:
        return []
    normalized = []
    seen = set()
    source = values if isinstance(values, list) else [values]
    for value in source:
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        value = value.strip()[:200]
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
        if len(normalized) >= 50:
            break
    return normalized

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
    entry, changed = migrate_memory_entry(longterm_memory.get(user_id))
    if changed or user_id not in longterm_memory:
        longterm_memory[user_id] = entry
    return entry

def memory_has_content(entry):
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

def normalize_auto_memory_operations(operations):
    if not isinstance(operations, list):
        return [], ["memory_operations がリストではない"]

    normalized = []
    errors = []
    seen = set()
    for index, operation in enumerate(operations[:10]):
        label = f"operation {index + 1}"
        if not isinstance(operation, dict) or operation.get("type") != "add_item":
            errors.append(f"{label}: 自動記憶では add_item だけ使用できる")
            continue
        raw_category = operation.get("category")
        category = canonicalize_memory_category(raw_category)
        item = operation.get("item")
        if not category:
            errors.append(f"{label}: category が使用できない")
            continue
        if not isinstance(item, str):
            errors.append(f"{label}: item は文字列にする")
            continue
        item = item.strip()
        if not item or len(item) > 200:
            errors.append(f"{label}: item は1〜200文字にする")
            continue
        _, item = canonicalize_memory_item(raw_category, item)
        key = (category, item)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({
            "type": "add_item",
            "category": category,
            "item": item,
        })

    if len(operations) > 10:
        errors.append("一度に自動記憶できる項目は10件まで")
    if errors:
        return [], errors
    return normalized, []

def prepare_memory_edit_operations(operations, entry):
    if not isinstance(operations, list):
        return [], ["operations がリストではない"]
    if len(operations) > 10:
        return [], ["一度に提案できる操作は10件まで"]

    items = entry.get("items", {}) if isinstance(entry, dict) else {}
    slots = entry.get("slots", {}) if isinstance(entry, dict) else {}
    prepared = []
    errors = []
    affected = set()

    for index, operation in enumerate(operations):
        label = f"operation {index + 1}"
        if not isinstance(operation, dict):
            errors.append(f"{label} がオブジェクトではない")
            continue
        operation_type = str(operation.get("type", "")).strip()

        if operation_type == "set_slot":
            slot = str(operation.get("slot", "")).strip().lower()
            value = operation.get("value")
            if slot not in MEMORY_SLOT_NAMES:
                errors.append(f"{label}: 使用できないslot")
                continue
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > 100:
                errors.append(f"{label}: slotの値は1〜100文字にする")
                continue
            if ("slot", slot) in affected:
                errors.append(f"{label}: 同じslotを複数回変更できない")
                continue
            affected.add(("slot", slot))
            prepared.append({
                "type": "set_slot",
                "slot": slot,
                "value": value.strip(),
                "expected_exists": slot in slots,
                "expected_value": slots.get(slot),
            })
            continue

        if operation_type == "delete_slot":
            slot = str(operation.get("slot", "")).strip().lower()
            if slot not in MEMORY_SLOT_NAMES or slot not in slots:
                errors.append(f"{label}: 削除対象のslotが見つからない")
                continue
            if ("slot", slot) in affected:
                errors.append(f"{label}: 同じslotを複数回変更できない")
                continue
            affected.add(("slot", slot))
            prepared.append({
                "type": "delete_slot",
                "slot": slot,
                "expected_value": slots[slot],
            })
            continue

        if operation_type == "delete_matching_items":
            query = operation.get("query")
            if not isinstance(query, str) or not query.strip():
                errors.append(f"{label}: 検索語がない")
                continue
            query = query.strip()
            raw_category = operation.get("category")
            category = (
                canonicalize_memory_category(raw_category)
                if raw_category
                else None
            )
            categories = [category] if category else list(items.keys())
            targets = []
            for target_category in categories:
                for value in normalize_item_list(items.get(target_category, [])):
                    if query.casefold() in value.casefold():
                        targets.append({
                            "category": target_category,
                            "item": value,
                        })
            if not targets:
                errors.append(f"{label}: 「{query}」に一致する記憶がない")
                continue
            if any(
                ("category", target["category"]) in affected
                or ("item", target["category"], target["item"]) in affected
                for target in targets
            ):
                errors.append(f"{label}: 同じ項目を複数回変更できない")
                continue
            for target in targets:
                affected.add(("item", target["category"], target["item"]))
            prepared.append({
                "type": "delete_matching_items",
                "query": query,
                "targets": targets,
            })
            continue

        raw_category = operation.get("category")
        category = canonicalize_memory_category(raw_category)
        if not category:
            errors.append(f"{label}: category が使用できない")
            continue
        current_values = normalize_item_list(items.get(category, []))
        if ("category", category) in affected:
            errors.append(f"{label}: 同じcategoryを複数回変更できない")
            continue

        if operation_type == "add_item":
            item = operation.get("item")
            if not isinstance(item, str) or not item.strip() or len(item.strip()) > 200:
                errors.append(f"{label}: item は1〜200文字にする")
                continue
            item = item.strip()
            _, item = canonicalize_memory_item(raw_category, item)
            if item in current_values:
                errors.append(f"{label}: その項目はすでに存在する")
                continue
            if ("item", category, item) in affected:
                errors.append(f"{label}: 同じ項目を複数回変更できない")
                continue
            affected.add(("item", category, item))
            prepared.append({
                "type": "add_item",
                "category": category,
                "item": item,
            })
            continue

        if operation_type == "delete_item":
            item = operation.get("item")
            if isinstance(item, str):
                _, item = canonicalize_memory_item(raw_category, item)
            if not isinstance(item, str) or item not in current_values:
                errors.append(f"{label}: 完全一致する削除対象がない")
                continue
            if ("item", category, item) in affected:
                errors.append(f"{label}: 同じ項目を複数回変更できない")
                continue
            affected.add(("item", category, item))
            prepared.append({
                "type": "delete_item",
                "category": category,
                "item": item,
            })
            continue

        if operation_type == "rewrite_item":
            old_item = operation.get("old_item")
            new_item = operation.get("new_item")
            if isinstance(old_item, str):
                _, old_item = canonicalize_memory_item(raw_category, old_item)
            if not isinstance(old_item, str) or old_item not in current_values:
                errors.append(f"{label}: 書き換え元が完全一致しない")
                continue
            if (
                not isinstance(new_item, str)
                or not new_item.strip()
                or len(new_item.strip()) > 200
            ):
                errors.append(f"{label}: 書き換え先は1〜200文字にする")
                continue
            new_item = new_item.strip()
            _, new_item = canonicalize_memory_item(raw_category, new_item)
            if new_item != old_item and new_item in current_values:
                errors.append(f"{label}: 書き換え先がすでに存在する")
                continue
            if ("item", category, old_item) in affected:
                errors.append(f"{label}: 同じ項目を複数回変更できない")
                continue
            affected.add(("item", category, old_item))
            prepared.append({
                "type": "rewrite_item",
                "category": category,
                "old_item": old_item,
                "new_item": new_item,
            })
            continue

        if operation_type == "clear_category":
            if not current_values:
                errors.append(f"{label}: categoryが空か存在しない")
                continue
            if ("category", category) in affected or any(
                key[0] == "item" and key[1] == category for key in affected
            ):
                errors.append(f"{label}: 同じcategoryを複数回変更できない")
                continue
            affected.add(("category", category))
            prepared.append({
                "type": "clear_category",
                "category": category,
                "expected_items": current_values,
            })
            continue

        errors.append(f"{label}: 許可されていない操作 {operation_type!r}")

    if errors:
        return [], errors
    if not prepared:
        return [], ["実行できる操作がない"]
    return prepared, []

def canonicalize_memory_operation(operation):
    if not isinstance(operation, dict):
        return operation
    normalized = deepcopy(operation)
    raw_category = normalized.get("category")
    if raw_category:
        category = canonicalize_memory_category(raw_category)
        if category:
            normalized["category"] = category
            for key in ("item", "old_item", "new_item"):
                if isinstance(normalized.get(key), str):
                    _, normalized[key] = canonicalize_memory_item(
                        raw_category,
                        normalized[key],
                    )
            if isinstance(normalized.get("expected_items"), list):
                normalized["expected_items"] = normalize_item_list([
                    canonicalize_memory_item(raw_category, item)[1]
                    for item in normalized["expected_items"]
                    if isinstance(item, str)
                ])
    if isinstance(normalized.get("targets"), list):
        targets = []
        for target in normalized["targets"]:
            if not isinstance(target, dict):
                continue
            raw_target_category = target.get("category")
            category, item = canonicalize_memory_item(
                raw_target_category,
                target.get("item"),
            )
            if category and isinstance(item, str):
                targets.append({
                    **target,
                    "category": category,
                    "item": item,
                })
        normalized["targets"] = targets
    return normalized

def describe_memory_operation(operation):
    operation = canonicalize_memory_operation(operation)
    operation_type = operation.get("type")
    category_label = memory_category_label(operation.get("category"))
    if operation_type == "add_item":
        return f"{category_label}に「{operation.get('item')}」を追加"
    if operation_type == "delete_item":
        return f"{category_label}から「{operation.get('item')}」を削除"
    if operation_type == "delete_matching_items":
        return (
            f"「{operation.get('query')}」に一致する"
            f"{len(operation.get('targets', []))}件を削除"
        )
    if operation_type == "rewrite_item":
        return (
            f"{category_label}の「{operation.get('old_item')}」を"
            f"「{operation.get('new_item')}」へ書き換え"
        )
    if operation_type == "set_slot":
        slot_label = memory_slot_label(operation.get("slot"))
        if operation.get("expected_exists"):
            return (
                f"{slot_label}の「{operation.get('expected_value')}」を"
                f"「{operation.get('value')}」へ書き換え"
            )
        return f"{slot_label}を「{operation.get('value')}」に設定"
    if operation_type == "delete_slot":
        slot_label = memory_slot_label(operation.get("slot"))
        return (
            f"{slot_label}の"
            f"「{operation.get('expected_value')}」を削除"
        )
    if operation_type == "clear_category":
        return (
            f"{category_label}の"
            f"{len(operation.get('expected_items', []))}件をすべて削除"
        )
    return "読み取れない操作"

def append_memory_change(entry, source, summary, changes):
    change_log = entry.get("change_log")
    if not isinstance(change_log, list):
        change_log = []
    change_log.append({
        "id": uuid.uuid4().hex[:8],
        "created_at": datetime.now().isoformat(),
        "source": source,
        "summary": str(summary or "").strip()[:300],
        "changes": [
            canonicalize_memory_operation(change)
            for change in changes
            if isinstance(change, dict)
        ],
    })
    entry["change_log"] = change_log[-MAX_MEMORY_CHANGE_LOG:]

async def persist_memory_entry(user_id, entry, commit_message):
    had_original = user_id in longterm_memory
    original = longterm_memory.get(user_id)
    longterm_memory[user_id] = entry
    try:
        await write_json_async(longterm_memory_file, longterm_memory)
    except Exception:
        if had_original:
            longterm_memory[user_id] = original
        else:
            longterm_memory.pop(user_id, None)
        raise
    await save_to_git_async(commit_message)

async def apply_auto_memory_operations(user_id, operations):
    normalized, errors = normalize_auto_memory_operations(operations)
    if errors:
        return {"changes": [], "errors": errors}

    async with memory_lock:
        entry = deepcopy(ensure_memory_entry(user_id))
        items = entry["items"]
        changes = []
        for operation in normalized:
            category = operation["category"]
            item = operation["item"]
            current_values = normalize_item_list(items.get(category, []))
            if category not in items and len(items) >= 30:
                continue
            if item in current_values or len(current_values) >= 50:
                continue
            current_values.append(item)
            items[category] = current_values
            changes.append(operation.copy())

        if not changes:
            return {"changes": [], "errors": []}

        for change in changes:
            change["expected_items"] = list(items[change["category"]])
        summary = "、".join(
            f"{change['category']}の「{change['item']}」"
            for change in changes
        )
        append_memory_change(entry, "auto", summary, changes)
        entry["updated"] = datetime.now().isoformat()
        await persist_memory_entry(user_id, entry, "auto memory")
        return {"changes": changes, "errors": []}

def format_auto_memory_debug_summary(proposed_count, result):
    errors = result.get("errors", []) if isinstance(result, dict) else []
    changes = result.get("changes", []) if isinstance(result, dict) else []
    if errors:
        lines = [f"rejected: {proposed_count}件"]
        lines.extend(f"・{error}" for error in errors[:10])
        return "\n".join(lines)
    if changes:
        lines = [f"accepted: {len(changes)}件 / proposed: {proposed_count}件"]
        lines.extend(
            f"・{describe_memory_operation(change)}"
            for change in changes
            if isinstance(change, dict)
        )
        return "\n".join(lines)
    return f"accepted: 0件 / proposed: {proposed_count}件"

def verify_memory_edit_operations(entry, operations):
    items = entry.get("items", {})
    slots = entry.get("slots", {})
    conflicts = []
    for operation in operations:
        operation_type = operation["type"]
        if operation_type == "add_item":
            continue
        if operation_type == "set_slot":
            slot = operation["slot"]
            exists = slot in slots
            if (
                exists != operation.get("expected_exists")
                or slots.get(slot) != operation.get("expected_value")
            ):
                conflicts.append(slot)
        elif operation_type == "delete_slot":
            if slots.get(operation["slot"]) != operation.get("expected_value"):
                conflicts.append(operation["slot"])
        elif operation_type == "delete_item":
            if operation["item"] not in items.get(operation["category"], []):
                conflicts.append(f"{operation['category']}: {operation['item']}")
        elif operation_type == "delete_matching_items":
            for target in operation["targets"]:
                if target["item"] not in items.get(target["category"], []):
                    conflicts.append(f"{target['category']}: {target['item']}")
        elif operation_type == "rewrite_item":
            values = items.get(operation["category"], [])
            if (
                operation["old_item"] not in values
                or (
                    operation["new_item"] != operation["old_item"]
                    and operation["new_item"] in values
                )
            ):
                conflicts.append(f"{operation['category']}: {operation['old_item']}")
        elif operation_type == "clear_category":
            if (
                normalize_item_list(items.get(operation["category"], []))
                != operation["expected_items"]
            ):
                conflicts.append(operation["category"])
    return conflicts

async def apply_memory_edit_operations(user_id, operations, summary):
    async with memory_lock:
        entry = deepcopy(ensure_memory_entry(user_id))
        conflicts = verify_memory_edit_operations(entry, operations)
        if conflicts:
            return {"changes": [], "conflicts": conflicts, "errors": []}

        items = entry["items"]
        slots = entry["slots"]
        changes = []
        for operation in operations:
            operation_type = operation["type"]
            if operation_type == "add_item":
                category = operation["category"]
                values = normalize_item_list(items.get(category, []))
                if operation["item"] not in values:
                    values.append(operation["item"])
                    items[category] = values
                    changes.append(operation)
            elif operation_type == "delete_item":
                category = operation["category"]
                values = list(items.get(category, []))
                values.remove(operation["item"])
                if values:
                    items[category] = values
                else:
                    items.pop(category, None)
                changes.append(operation)
            elif operation_type == "delete_matching_items":
                for target in operation["targets"]:
                    category = target["category"]
                    values = list(items.get(category, []))
                    values.remove(target["item"])
                    if values:
                        items[category] = values
                    else:
                        items.pop(category, None)
                changes.append(operation)
            elif operation_type == "rewrite_item":
                category = operation["category"]
                values = list(items.get(category, []))
                index = values.index(operation["old_item"])
                values[index] = operation["new_item"]
                items[category] = normalize_item_list(values)
                changes.append(operation)
            elif operation_type == "set_slot":
                before_exists = operation["slot"] in slots
                before_value = slots.get(operation["slot"])
                slots[operation["slot"]] = operation["value"]
                change = operation.copy()
                change["before_exists"] = before_exists
                change["before_value"] = before_value
                changes.append(change)
            elif operation_type == "delete_slot":
                before_value = slots.pop(operation["slot"])
                change = operation.copy()
                change["before_value"] = before_value
                changes.append(change)
            elif operation_type == "clear_category":
                items.pop(operation["category"], None)
                changes.append(operation)

        if not changes:
            return {"changes": [], "conflicts": [], "errors": []}

        append_memory_change(entry, "edit", summary, changes)
        entry["updated"] = datetime.now().isoformat()
        await persist_memory_entry(user_id, entry, "edit memory")
        return {"changes": changes, "conflicts": [], "errors": []}

def format_recent_memory_changes(entry, limit=10):
    change_log = entry.get("change_log", []) if isinstance(entry, dict) else []
    lines = []
    for change in reversed(change_log[-limit:]):
        if not isinstance(change, dict):
            continue
        marker = "↩️" if change.get("undone_at") else "📌"
        source = "自動" if change.get("source") == "auto" else "手動"
        created_at = str(change.get("created_at", ""))[:16].replace("T", " ")
        descriptions = [
            describe_memory_operation(operation)
            for operation in change.get("changes", [])
            if isinstance(operation, dict)
        ]
        summary = discord.utils.escape_mentions(
            "／".join(descriptions)
            or str(change.get("summary") or "変更内容なし")
        )
        lines.append(f"{marker} [{source}] {created_at} {summary}")
    return lines

async def undo_latest_auto_memory(user_id):
    async with memory_lock:
        entry = deepcopy(ensure_memory_entry(user_id))
        change_log = entry.get("change_log", [])
        target = next(
            (
                change for change in reversed(change_log)
                if change.get("source") == "auto" and not change.get("undone_at")
            ),
            None,
        )
        if target is None:
            return {"undone": False, "reason": "not_found"}

        items = entry["items"]
        normalized_changes = []
        for raw_change in target.get("changes", []):
            change = canonicalize_memory_operation(raw_change)
            if not isinstance(change, dict) or change.get("type") != "add_item":
                return {"undone": False, "reason": "unsupported"}
            current_items = normalize_item_list(
                items.get(change.get("category"), [])
            )
            has_expected_items = isinstance(
                raw_change.get("expected_items"),
                list,
            )
            expected_items = normalize_item_list(change.get("expected_items"))
            raw_category = raw_change.get("category")
            category_was_migrated = (
                raw_category != change.get("category")
            )
            item_exists = change.get("item") in current_items
            if not has_expected_items:
                is_safe = item_exists
            elif category_was_migrated:
                is_safe = (
                    item_exists
                    and all(item in current_items for item in expected_items)
                )
            else:
                is_safe = item_exists and current_items == expected_items
            if not is_safe:
                return {"undone": False, "reason": "conflict"}
            normalized_changes.append(change)

        for change in normalized_changes:
            category = change["category"]
            values = list(items.get(category, []))
            values.remove(change["item"])
            if values:
                items[category] = values
            else:
                items.pop(category, None)

        target["undone_at"] = datetime.now().isoformat()
        entry["updated"] = datetime.now().isoformat()
        await persist_memory_entry(user_id, entry, "undo auto memory")
        return {"undone": True, "change": target}
