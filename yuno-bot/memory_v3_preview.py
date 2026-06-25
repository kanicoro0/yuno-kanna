"""Dry-run helpers for previewing a future memory schema v3.

This module must not mutate or persist memory data.  It converts the current
schema v2 entry into a v3-shaped object so the UI can inspect and validate the
shape before any migration is attempted.
"""

from memory_model import (
    MEMORY_CATEGORY_ORDER,
    MEMORY_SLOT_NAMES,
    normalize_item_list,
)


INTERACTION_PREFERENCE_CATEGORIES = {
    "傾向",
    "好み",
    "話し方",
    "避けたいこと",
}

KEYWORD_MAX_LENGTH = 12
KEYWORD_SENTENCE_MARKERS = (
    " ",
    "　",
    "、",
    "。",
    "，",
    "．",
    ":",
    "：",
    "について",
    "として",
    "という",
    "ように",
    "くらい",
    "ではない",
    "がよい",
    "している",
    "伝わる",
    "追う",
    "追いかける",
)

RECORD_COLLECTIONS = (
    ("memories", "m"),
    ("keywords", "k"),
    ("interaction_preferences", "h"),
)


def looks_like_keyword(value):
    text = str(value or "").strip()
    if not text:
        return False
    if len(text) > KEYWORD_MAX_LENGTH:
        return False
    return not any(marker in text for marker in KEYWORD_SENTENCE_MARKERS)


def _new_record(prefix, index, text, source_category):
    record_id = f"{prefix}_{index:03d}"
    return record_id, {
        "id": record_id,
        "text": text,
        "status": "active",
        "source_schema": 2,
        "source_category": source_category,
    }


def _add_record(target, prefix, text, source_category):
    record_id, record = _new_record(
        prefix,
        len(target) + 1,
        text,
        source_category,
    )
    target[record_id] = record


def build_memory_v3_preview(entry):
    """Build a v3-shaped dry-run object from a schema v2 memory entry.

    The returned object is intentionally close to a future persisted structure,
    but it is never written back by this function.
    """
    preview = {
        "schema_version": 3,
        "dry_run": True,
        "source_schema_version": entry.get("schema_version") if isinstance(entry, dict) else None,
        "slots": {},
        "memories": {},
        "keywords": {},
        "interaction_preferences": {},
        "change_log": [],
    }
    if not isinstance(entry, dict):
        return preview

    slots = entry.get("slots")
    if isinstance(slots, dict):
        for slot in MEMORY_SLOT_NAMES:
            value = slots.get(slot)
            if value:
                preview["slots"][slot] = str(value)

    items = entry.get("items")
    if not isinstance(items, dict):
        return preview

    seen = set()
    ordered_categories = list(MEMORY_CATEGORY_ORDER)
    extra_categories = [
        category for category in items.keys()
        if category not in MEMORY_CATEGORY_ORDER
    ]

    for category in ordered_categories + extra_categories:
        values = normalize_item_list(items.get(category, []))
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            if category in INTERACTION_PREFERENCE_CATEGORIES:
                _add_record(
                    preview["interaction_preferences"],
                    "h",
                    value,
                    category,
                )
            elif looks_like_keyword(value):
                _add_record(preview["keywords"], "k", value, category)
            else:
                _add_record(preview["memories"], "m", value, category)

    return preview


def summarize_memory_v3_preview(preview):
    if not isinstance(preview, dict):
        return {
            "slots": 0,
            "memories": 0,
            "keywords": 0,
            "interaction_preferences": 0,
            "total_records": 0,
        }
    counts = {
        "slots": len(preview.get("slots", {})) if isinstance(preview.get("slots"), dict) else 0,
    }
    total_records = 0
    for collection, _prefix in RECORD_COLLECTIONS:
        records = preview.get(collection)
        count = len(records) if isinstance(records, dict) else 0
        counts[collection] = count
        total_records += count
    counts["total_records"] = total_records
    return counts


def validate_memory_v3_preview(preview):
    """Validate the dry-run v3 object without mutating it."""
    errors = []
    warnings = []

    if not isinstance(preview, dict):
        return {
            "ok": False,
            "errors": ["preview is not an object"],
            "warnings": [],
            "counts": summarize_memory_v3_preview(preview),
        }

    if preview.get("schema_version") != 3:
        errors.append("schema_version must be 3")
    if preview.get("dry_run") is not True:
        warnings.append("dry_run is not true")

    slots = preview.get("slots")
    if not isinstance(slots, dict):
        errors.append("slots must be an object")
    else:
        for slot, value in slots.items():
            if slot not in MEMORY_SLOT_NAMES:
                warnings.append(f"unknown slot: {slot}")
            if not isinstance(value, str) or not value.strip():
                errors.append(f"slot {slot} must be a non-empty string")

    seen_ids = set()
    seen_texts = set()
    for collection, prefix in RECORD_COLLECTIONS:
        records = preview.get(collection)
        if not isinstance(records, dict):
            errors.append(f"{collection} must be an object")
            continue
        for record_id, record in records.items():
            if record_id in seen_ids:
                errors.append(f"duplicate record id: {record_id}")
            seen_ids.add(record_id)
            if not isinstance(record_id, str) or not record_id.startswith(f"{prefix}_"):
                errors.append(f"{collection} has invalid id: {record_id}")
            if not isinstance(record, dict):
                errors.append(f"{record_id} must be an object")
                continue
            if record.get("id") != record_id:
                errors.append(f"{record_id} id field does not match key")
            text = record.get("text")
            if not isinstance(text, str) or not text.strip():
                errors.append(f"{record_id} text must be a non-empty string")
            elif text in seen_texts:
                warnings.append(f"duplicate text across records: {text}")
            else:
                seen_texts.add(text)
            if record.get("status") != "active":
                errors.append(f"{record_id} status must be active")
            if record.get("source_schema") != 2:
                warnings.append(f"{record_id} source_schema is not 2")
            if not record.get("source_category"):
                warnings.append(f"{record_id} has no source_category")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": summarize_memory_v3_preview(preview),
    }


def _format_records(title, records):
    lines = []
    if not records:
        return lines
    lines.append(title)
    for record in records.values():
        source = record.get("source_category")
        source_suffix = f" [{source}]" if source else ""
        lines.append(f"{record['id']}: {record['text']}{source_suffix}")
    return lines


def format_memory_v3_preview(preview):
    """Format a v3 dry-run object for ephemeral Discord display."""
    if not isinstance(preview, dict):
        return [
            "🧪 v3 preview / dry run",
            "保存形式はまだ変更していないよ",
            "",
            "（previewの生成に失敗したよ）",
        ]

    lines = [
        "🧪 v3 preview / dry run",
        "保存形式はまだ変更していないよ",
        f"schema_version: {preview.get('schema_version')}",
        f"source_schema_version: {preview.get('source_schema_version')}",
    ]

    slots = preview.get("slots")
    if isinstance(slots, dict) and slots:
        lines.append("")
        lines.append("slots")
        for slot, value in slots.items():
            lines.append(f"・{slot}: {value}")

    for title, key in (
        ("memories", "memories"),
        ("keywords", "keywords"),
        ("interaction_preferences", "interaction_preferences"),
    ):
        records = preview.get(key)
        if not isinstance(records, dict):
            continue
        record_lines = _format_records(title, records)
        if record_lines:
            lines.append("")
            lines.extend(record_lines)

    if len(lines) <= 4:
        lines.append("")
        lines.append("（まだpreviewできる記憶がないよ）")
    return lines


def format_memory_v3_validation(validation):
    """Format validation results for ephemeral Discord display."""
    if not isinstance(validation, dict):
        return [
            "🧪 v3 validate / dry run",
            "保存形式はまだ変更していないよ",
            "",
            "❌ validation result is invalid",
        ]

    counts = validation.get("counts", {}) if isinstance(validation.get("counts"), dict) else {}
    lines = [
        "🧪 v3 validate / dry run",
        "保存形式はまだ変更していないよ",
        "✅ OK" if validation.get("ok") else "❌ NG",
        "",
        "counts",
        f"・slots: {counts.get('slots', 0)}",
        f"・memories: {counts.get('memories', 0)}",
        f"・keywords: {counts.get('keywords', 0)}",
        f"・interaction_preferences: {counts.get('interaction_preferences', 0)}",
        f"・total_records: {counts.get('total_records', 0)}",
    ]

    errors = validation.get("errors")
    if isinstance(errors, list) and errors:
        lines.append("")
        lines.append("errors")
        lines.extend(f"・{error}" for error in errors[:20])
        if len(errors) > 20:
            lines.append(f"・ほか{len(errors) - 20}件")

    warnings = validation.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.append("")
        lines.append("warnings")
        lines.extend(f"・{warning}" for warning in warnings[:20])
        if len(warnings) > 20:
            lines.append(f"・ほか{len(warnings) - 20}件")

    return lines
