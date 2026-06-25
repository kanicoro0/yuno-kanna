from config import DISCORD_GUILD_ID, DISCORD_LIMIT, ENABLE_GIT_SAVE, OWNER_ID
from memory_model import (
    MEMORY_CATEGORY_ORDER,
    MEMORY_SLOT_NAMES,
    ensure_memory_entry,
    memory_has_content,
    memory_slot_label,
    normalize_item_list,
)
from memory_v3_preview import (
    build_memory_v3_preview,
    format_memory_v3_export,
    format_memory_v3_preview,
    format_memory_v3_validation,
    validate_memory_v3_preview,
)


chat_history = {}
guild_notes = {}
persisted_reminders = {}


FLAT_HANDLING_CATEGORIES = {
    "傾向",
    "好み",
    "話し方",
    "避けたいこと",
}

FRAGMENT_MAX_LENGTH = 12
FRAGMENT_SENTENCE_MARKERS = (
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


def configure(*, history, notes, persisted):
    global chat_history, guild_notes, persisted_reminders
    chat_history = history
    guild_notes = notes
    persisted_reminders = persisted


def _append_section(lines, title, values):
    cleaned = [value for value in values if str(value).strip()]
    if not cleaned:
        return
    if lines:
        lines.append("")
    lines.append(title)
    lines.extend(f"・{value}" for value in cleaned)


def _append_unique(target, seen, values):
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        target.append(value)


def _looks_like_fragment(value):
    text = str(value or "").strip()
    if not text:
        return False
    if len(text) > FRAGMENT_MAX_LENGTH:
        return False
    return not any(marker in text for marker in FRAGMENT_SENTENCE_MARKERS)


def _append_memory_items(*, target, fragments, handling, seen, category, values):
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        if category in FLAT_HANDLING_CATEGORIES:
            handling.append(value)
        elif _looks_like_fragment(value):
            fragments.append(value)
        else:
            target.append(value)


def _split_memory_by_preview_role(entry):
    remembered = []
    fragments = []
    handling = []
    seen_items = set()

    items = entry.get("items") if isinstance(entry, dict) else None
    if not isinstance(items, dict):
        return remembered, fragments, handling

    for category in MEMORY_CATEGORY_ORDER:
        _append_memory_items(
            target=remembered,
            fragments=fragments,
            handling=handling,
            seen=seen_items,
            category=category,
            values=normalize_item_list(items.get(category, [])),
        )

    # canonical外のカテゴリが残っていても、previewでは落とさず saved 側へ寄せる。
    for category, values in items.items():
        if category in MEMORY_CATEGORY_ORDER:
            continue
        _append_memory_items(
            target=remembered,
            fragments=fragments,
            handling=handling,
            seen=seen_items,
            category=category,
            values=normalize_item_list(values),
        )

    return remembered, fragments, handling


def format_memory_flat_sections(entry):
    """schema v2のまま、表示上だけ薄く役割別に並べる。"""
    if not isinstance(entry, dict):
        return []

    lines = []
    slot_lines = []
    slots = entry.get("slots")
    if isinstance(slots, dict):
        for slot in MEMORY_SLOT_NAMES:
            value = slots.get(slot)
            if not value:
                continue
            if slot == "preferred_name":
                slot_lines.append(str(value))
            else:
                slot_lines.append(f"{memory_slot_label(slot)}: {value}")

    remembered, fragments, handling = _split_memory_by_preview_role(entry)

    _append_section(lines, "呼び名", slot_lines)
    _append_section(lines, "覚えていること", remembered)
    _append_section(lines, "断片", fragments)
    _append_section(lines, "話し方・扱い方", handling)
    return lines


YUNO_GUIDE = """ゆのが使えるコマンドの一覧
・/memory show：現在の個人記憶を本人だけに表示
・/memory show_flat：現在の個人記憶をカテゴリ棚なしで表示
・/memory preview_v3：現在の個人記憶をv3風に仮表示
・/memory validate_v3：v3仮変換が安全な形か確認
・/memory export_v3：v3仮変換JSONを確認
・/memory edit：記憶一覧を開いて追加・編集・削除
・/memory edit instruction：自然な言葉で変更案を作り、確認後に実行
・/memory recent：最近の自動記憶・手動編集履歴を表示
・/memory undo：直近の記憶変更を取り消す
・/servermemory show：このサーバーのメモを表示
・/servermemory set content：管理できる人がサーバーメモを更新
・/remind time message：指定した時間にリマインド
・/reminders：設定中のリマインドを本人だけに表示
・/cancelremind：リマインドをキャンセル
・/status：自分に関係する保存状態を本人だけに表示
・/guide：この一覧を表示

@でメンションされると会話が始まるよ
📌 は記憶を追加した合図
🗑️ は記憶を削除した合図
📝 は記憶を書き換えた、または呼び名などを変更した合図
詳しい変更内容は /memory recent で確認できるよ
直近の記憶変更は /memory undo で戻せるよ
リマインド通知本体は、指定したチャンネルに届くよ
なにかあったら k.a.256 (X・Discord共通: _k256) まで"""


async def slash_guide(interaction):
    await interaction.response.send_message(YUNO_GUIDE, ephemeral=True)


async def slash_memory_show_flat(interaction):
    user_id = str(interaction.user.id)
    entry = ensure_memory_entry(user_id)
    lines = [f"📘 {interaction.user.display_name} の記憶（フラット表示）："]
    lines.extend(format_memory_flat_sections(entry) or ["（まだ何も覚えていないよ）"])
    await interaction.response.send_message(
        "\n".join(lines)[:DISCORD_LIMIT],
        ephemeral=True,
    )


async def slash_memory_preview_v3(interaction):
    user_id = str(interaction.user.id)
    entry = ensure_memory_entry(user_id)
    preview = build_memory_v3_preview(entry)
    await interaction.response.send_message(
        "\n".join(format_memory_v3_preview(preview))[:DISCORD_LIMIT],
        ephemeral=True,
    )


async def slash_memory_validate_v3(interaction):
    user_id = str(interaction.user.id)
    entry = ensure_memory_entry(user_id)
    preview = build_memory_v3_preview(entry)
    validation = validate_memory_v3_preview(preview)
    await interaction.response.send_message(
        "\n".join(format_memory_v3_validation(validation))[:DISCORD_LIMIT],
        ephemeral=True,
    )


async def slash_memory_export_v3(interaction):
    user_id = str(interaction.user.id)
    entry = ensure_memory_entry(user_id)
    preview = build_memory_v3_preview(entry)
    validation = validate_memory_v3_preview(preview)
    await interaction.response.send_message(
        "\n".join(format_memory_v3_export(preview, validation, limit=DISCORD_LIMIT))[:DISCORD_LIMIT],
        ephemeral=True,
    )


async def slash_status(interaction):
    user_id = str(interaction.user.id)
    history = chat_history.get(user_id)
    history_count = len(history) if isinstance(history, list) else 0
    memory = ensure_memory_entry(user_id)
    has_server_memory = bool(
        interaction.guild is not None
        and guild_notes.get(str(interaction.guild.id))
    )
    lines = [
        "🔎 ゆのの動作状態：",
        f"・会話履歴件数：{history_count}",
        f"・個人記憶：{'あり' if memory_has_content(memory) else 'なし'}",
        f"・記憶変更履歴：{len(memory.get('change_log', []))}件",
        f"・設定中リマインド：{'あり' if user_id in persisted_reminders else 'なし'}",
        f"・サーバーメモ：{'あり' if has_server_memory else 'なし'}",
    ]
    if user_id == str(OWNER_ID):
        sync_target = (
            f"guild ({DISCORD_GUILD_ID})" if DISCORD_GUILD_ID else "global"
        )
        lines.extend([
            f"・sync先：{sync_target}",
            f"・Git保存：{'有効' if ENABLE_GIT_SAVE else '無効'}",
        ])
    await interaction.response.send_message("\n".join(lines), ephemeral=True)
