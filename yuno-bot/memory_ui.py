from copy import deepcopy
import json

import discord

from config import DISCORD_LIMIT
from openai_client import oa_chat
from memory_model import (
    MEMORY_CATEGORY_GUIDANCE,
    MEMORY_CATEGORY_ORDER,
    MEMORY_ITEM_PAGE_SIZE,
    apply_memory_edit_operations,
    describe_memory_operation,
    ensure_memory_entry,
    format_memory_record_detail_for_display,
    format_memory_flat_sections_for_user,
    format_memory_records_for_display,
    format_recent_memory_changes,
    memory_category_display_group,
    memory_category_label,
    memory_slot_label,
    normalize_item_list,
    ordered_memory_categories,
    prepare_memory_edit_operations,
    undo_latest_memory_change,
)


safe_report_error = print

MEMORY_EDIT_GROUPS = (
    ("slot", "preferred_name"),
    ("group", "覚えていること"),
    ("group", "話し方・扱い方"),
)

MEMORY_EDIT_GROUP_DEFAULT_CATEGORY = {
    "覚えていること": "覚え書き",
    "話し方・扱い方": "話し方",
}

MEMORY_EDIT_GROUP_DESCRIPTIONS = {
    "覚えていること": "事実、関心、作業、好きなもの",
    "話し方・扱い方": "返答態度、避けること、接し方",
}


def configure(*, error_reporter):
    global safe_report_error
    safe_report_error = error_reporter


memory_group = discord.app_commands.Group(
    name="memory",
    description="あなた個人の記憶を表示・編集します",
)

# /memory show は自然表示の主導線。旧カテゴリ別表示は通常導線から外す。
@memory_group.command(name="show", description="現在の個人記憶を自然な表示で確認します")
async def memory_show(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    lines = [f"📘 {interaction.user.display_name} の記憶："]
    lines.extend(
        format_memory_flat_sections_for_user(user_id)
        or ["まだ覚えていることはないみたい"]
    )
    await interaction.response.send_message(
        "\n".join(lines)[:DISCORD_LIMIT],
        ephemeral=True,
    )

@memory_group.command(name="recent", description="最近の記憶変更履歴を表示します")
async def memory_recent(interaction: discord.Interaction):
    entry = ensure_memory_entry(str(interaction.user.id))
    lines = format_recent_memory_changes(entry)
    content = (
        "🕰️ 最近の記憶変更：\n" + "\n".join(lines)
        if lines
        else "最近の記憶変更はまだないみたい"
    )
    await interaction.response.send_message(content[:DISCORD_LIMIT], ephemeral=True)


# records/record は保存実体を観測する管理表示。破壊的操作はここでは行わない。
@memory_group.command(name="records", description="記憶recordsを管理用に一覧表示します")
@discord.app_commands.describe(
    status="表示するrecord状態。省略時はactiveのみ",
    collection="表示するcollection。省略時はすべて",
    page="表示ページ",
)
@discord.app_commands.choices(
    status=[
        discord.app_commands.Choice(name="active", value="active"),
        discord.app_commands.Choice(name="deleted", value="deleted"),
        discord.app_commands.Choice(name="all", value="all"),
    ],
    collection=[
        discord.app_commands.Choice(name="all", value="all"),
        discord.app_commands.Choice(name="memories", value="memories"),
        discord.app_commands.Choice(name="keywords", value="keywords"),
        discord.app_commands.Choice(
            name="interaction_preferences",
            value="interaction_preferences",
        ),
    ],
)
async def memory_records(
    interaction: discord.Interaction,
    status: str = "active",
    collection: str = "all",
    page: int = 1,
):
    lines = format_memory_records_for_display(
        str(interaction.user.id),
        status=status,
        collection=collection,
        page=page,
        limit=DISCORD_LIMIT,
    )
    await interaction.response.send_message(
        "\n".join(lines)[:DISCORD_LIMIT],
        ephemeral=True,
    )


@memory_group.command(name="record", description="記憶recordを1件だけ詳しく表示します")
@discord.app_commands.describe(
    collection="recordのcollection",
    record_id="表示するrecord_id",
)
@discord.app_commands.choices(
    collection=[
        discord.app_commands.Choice(name="memories", value="memories"),
        discord.app_commands.Choice(name="keywords", value="keywords"),
        discord.app_commands.Choice(
            name="interaction_preferences",
            value="interaction_preferences",
        ),
    ],
)
async def memory_record(
    interaction: discord.Interaction,
    collection: str,
    record_id: str,
):
    lines = format_memory_record_detail_for_display(
        str(interaction.user.id),
        collection=collection,
        record_id=record_id,
        limit=DISCORD_LIMIT,
    )
    await interaction.response.send_message(
        "\n".join(lines)[:DISCORD_LIMIT],
        ephemeral=True,
    )


@memory_group.command(name="undo", description="直近の記憶変更を取り消します")
async def memory_undo(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    result = await undo_latest_memory_change(str(interaction.user.id))
    if result.get("undone"):
        descriptions = [
            describe_memory_operation(operation)
            for operation in result["change"].get("changes", [])
            if isinstance(operation, dict)
        ]
        summary = "／".join(descriptions) or "直近の記憶変更"
        content = f"↩️ 「{summary}」を取り消したよ"
    elif result.get("reason") == "conflict":
        content = "その記憶は後から変わっているため、安全に取り消せなかったよ"
    elif result.get("reason") == "unsupported":
        content = "その記憶変更は古い形式か広範囲操作のため、安全に取り消せなかったよ"
    else:
        content = "取り消せる記憶変更はないみたい"
    await interaction.followup.send(content, ephemeral=True)

def format_memory_edit_preview(summary, operations):
    explicit_summary = "／".join(
        describe_memory_operation(operation)
        for operation in operations
        if isinstance(operation, dict)
    ) or str(summary or "記憶を変更する")
    lines = [
        "🧭 記憶の変更案",
        f"内容: {discord.utils.escape_mentions(explicit_summary)}",
        "実行予定:",
    ]
    for operation in operations:
        lines.append(
            "・" + discord.utils.escape_mentions(
                describe_memory_operation(operation)
            )
        )
        if operation["type"] == "delete_matching_items":
            for target in operation["targets"][:10]:
                lines.append(
                    f"  - {memory_category_label(target['category'])}: "
                    f"{target['item']}"
                )
            if len(operation["targets"]) > 10:
                lines.append(f"  - ほか{len(operation['targets']) - 10}件")
        elif operation["type"] == "clear_category":
            for item in operation["expected_items"][:10]:
                lines.append(f"  - {item}")
            if len(operation["expected_items"]) > 10:
                lines.append(
                    f"  - ほか{len(operation['expected_items']) - 10}件"
                )
    return "\n".join(lines)[:DISCORD_LIMIT]

class MemoryEditConfirmView(discord.ui.View):
    def __init__(self, owner_user_id, summary, operations):
        super().__init__(timeout=600)
        self.owner_user_id = str(owner_user_id)
        self.summary = str(summary or "記憶を変更する")[:300]
        self.operations = deepcopy(operations)

    async def _check_owner(self, interaction):
        if str(interaction.user.id) == self.owner_user_id:
            return True
        await interaction.response.send_message(
            "これはきみの記憶変更案じゃないみたい",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="実行する", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction, button):
        if not await self._check_owner(interaction):
            return
        await interaction.response.defer()
        try:
            result = await apply_memory_edit_operations(
                self.owner_user_id,
                self.operations,
                self.summary,
            )
        except Exception as error:
            safe_report_error(f"記憶の編集に失敗: {error}")
            await interaction.edit_original_response(
                content="……記憶を変更できなかったみたい",
                view=None,
            )
            return
        if result["conflicts"]:
            content = (
                "確認中に対象の記憶が変わったため、何も変更しなかったよ。"
                "もう一度 /memory edit を使ってね"
            )
        elif result["changes"]:
            content = f"📝 {len(result['changes'])}件の操作を反映したよ"
        else:
            content = "変更する内容はなかったみたい"
        await interaction.edit_original_response(content=content, view=None)

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction, button):
        if not await self._check_owner(interaction):
            return
        await interaction.response.edit_message(
            content="記憶の変更をキャンセルしたよ",
            view=None,
        )

async def build_memory_instruction_proposal(instruction, entry):
    memory_snapshot = {
        "slots": entry.get("slots", {}),
        "items": entry.get("items", {}),
    }
    system_prompt = f"""個人記憶の変更案を作る。
現在の記憶:
{json.dumps(memory_snapshot, ensure_ascii=False, indent=2)}

使用できる記憶カテゴリ（categoryには必ずこの日本語名を使う）:
{json.dumps(MEMORY_CATEGORY_ORDER, ensure_ascii=False, indent=2)}
{MEMORY_CATEGORY_GUIDANCE}

必ず次のJSONだけを返す:
{{
  "summary": "変更案の短い説明",
  "ambiguous": false,
  "ambiguity_reason": "",
  "candidates": [],
  "operations": []
}}

使用できるoperation:
{{"type":"add_item","category":"作業","item":"Codexを使っている"}}
{{"type":"delete_item","category":"作業","item":"完全一致する既存項目"}}
{{"type":"delete_matching_items","query":"Codex"}}
{{"type":"delete_matching_items","query":"Codex","category":"作業"}}
{{"type":"rewrite_item","category":"覚え書き","old_item":"完全一致する既存項目","new_item":"新しい内容"}}
{{"type":"set_slot","slot":"preferred_name","value":"呼び名"}}
{{"type":"delete_slot","slot":"preferred_name"}}
{{"type":"clear_category","category":"作業"}}

規則:
・ユーザーの指示に必要な最小操作だけを出す
・削除や書き換えの対象は現在の記憶に基づける
・対象を一意に判断できなければ ambiguous=true にし、operationsは空にする
・ambiguous=true の場合は、考えられる対象をcandidatesへ短い文章で列挙する
・「整理して」のように残す基準が不明なら ambiguous=true にする
・存在しない内容を削除対象として作らない
・categoryは上記の日本語カテゴリだけを使う
・item / old_item / new_item は必ず1件の記憶だけを書く
・item / old_item / new_item 内に改行、箇条書き、複数項目の列挙を入れない
・複数のことを追加する場合は、複数のadd_item operationに分ける
・secret.xxxは使用しない
"""
    response = await oa_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": instruction},
        ],
        temperature=0,
        json_mode_hint=True,
    )
    proposal = json.loads(response.choices[0].message.content)
    if not isinstance(proposal, dict):
        raise ValueError("memory edit proposal is not an object")
    return proposal

def format_ambiguous_memory_proposal(proposal):
    reason = str(
        proposal.get("ambiguity_reason")
        or "変更対象をひとつに決められなかった"
    )[:500]
    candidates = proposal.get("candidates")
    candidate_lines = []
    if isinstance(candidates, list):
        candidate_lines = [
            "・" + discord.utils.escape_mentions(str(candidate)[:200])
            for candidate in candidates[:5]
            if str(candidate).strip()
        ]
    candidate_text = (
        "\n候補:\n" + "\n".join(candidate_lines)
        if candidate_lines
        else ""
    )
    return (
        "候補だけ確認したけれど、まだ実行できないみたい。\n"
        f"理由: {discord.utils.escape_mentions(reason)}"
        f"{candidate_text}\n"
        "対象や残したい内容をもう少し具体的に指定してね"
    )

class MemoryCategorySelect(discord.ui.Select):
    def __init__(self, editor_view, options):
        super().__init__(
            placeholder="記憶の種類を選ぶ",
            options=options,
            min_values=1,
            max_values=1,
            row=0,
        )
        self.editor_view = editor_view

    async def callback(self, interaction):
        if not await self.editor_view.check_owner(interaction):
            return
        target_type, target_name = self.values[0].split(":", 1)
        self.editor_view.selected_type = target_type
        self.editor_view.selected_name = target_name
        self.editor_view.selected_item = None
        self.editor_view.selected_item_category = None
        self.editor_view.item_page = 0
        self.editor_view.refresh_components()
        await interaction.response.edit_message(
            content=self.editor_view.render(),
            view=self.editor_view,
        )

class MemoryItemSelect(discord.ui.Select):
    def __init__(self, editor_view, entries, page_start):
        options = [
            discord.SelectOption(
                label=entry["item"][:100],
                value=str(page_start + index),
                default=(
                    editor_view.selected_item == entry["item"]
                    and editor_view.selected_item_category == entry["category"]
                ),
            )
            for index, entry in enumerate(entries)
        ]
        selected_item = editor_view.selected_item
        placeholder = (
            f"選択中: {selected_item[:90]}"
            if selected_item
            else "項目を選ぶ"
        )
        super().__init__(
            placeholder=placeholder,
            options=options,
            min_values=1,
            max_values=1,
            row=1,
        )
        self.editor_view = editor_view

    async def callback(self, interaction):
        if not await self.editor_view.check_owner(interaction):
            return
        entries = self.editor_view.current_item_entries()
        index = int(self.values[0])
        selected = entries[index] if 0 <= index < len(entries) else None
        self.editor_view.selected_item = selected["item"] if selected else None
        self.editor_view.selected_item_category = (
            selected["category"] if selected else None
        )
        self.editor_view.refresh_components()
        await interaction.response.edit_message(
            content=self.editor_view.render(),
            view=self.editor_view,
        )

class MemoryItemModal(discord.ui.Modal):
    def __init__(self, editor_view, mode):
        title = "記憶を追加" if mode == "add" else "記憶を書き換え"
        super().__init__(title=title, timeout=600)
        self.editor_view = editor_view
        self.mode = mode
        if mode == "edit" and editor_view.selected_type == "slot":
            default = editor_view.current_entry().get("slots", {}).get(
                editor_view.selected_name
            )
        else:
            default = editor_view.selected_item if mode == "edit" else None
        max_length = 100 if editor_view.selected_type == "slot" else 200
        self.value_input = discord.ui.TextInput(
            label="新しい内容",
            default=default,
            min_length=1,
            max_length=max_length,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction):
        if not await self.editor_view.check_owner(interaction):
            return
        entry = ensure_memory_entry(self.editor_view.owner_user_id)
        new_value = str(self.value_input.value).strip()
        if self.editor_view.selected_type == "slot":
            raw_operation = {
                "type": "set_slot",
                "slot": self.editor_view.selected_name,
                "value": new_value,
            }
        elif self.mode == "add":
            category = MEMORY_EDIT_GROUP_DEFAULT_CATEGORY.get(
                self.editor_view.selected_name,
                "覚え書き",
            )
            raw_operation = {
                "type": "add_item",
                "category": category,
                "item": new_value,
            }
        else:
            category = (
                self.editor_view.selected_item_category
                or MEMORY_EDIT_GROUP_DEFAULT_CATEGORY.get(
                    self.editor_view.selected_name,
                    "覚え書き",
                )
            )
            raw_operation = {
                "type": "rewrite_item",
                "category": category,
                "old_item": self.editor_view.selected_item,
                "new_item": new_value,
            }
        operations, errors = prepare_memory_edit_operations(
            [raw_operation],
            entry,
        )
        if errors:
            await interaction.response.send_message(
                "安全に変更案を作れなかったよ。\n"
                + "\n".join(f"・{error}" for error in errors[:5]),
                ephemeral=True,
            )
            return
        summary = describe_memory_operation(operations[0])
        if self.mode == "add" and self.editor_view.selected_type == "group":
            self.editor_view.selected_item = operations[0]["item"]
            self.editor_view.selected_item_category = operations[0]["category"]
        elif self.mode == "edit" and self.editor_view.selected_type == "group":
            self.editor_view.selected_item = operations[0]["new_item"]
            self.editor_view.selected_item_category = operations[0]["category"]
        await self.editor_view.apply_direct_operations(
            interaction,
            operations,
            summary,
        )

class MemoryEditView(discord.ui.View):
    def __init__(self, owner_user_id):
        super().__init__(timeout=600)
        self.owner_user_id = str(owner_user_id)
        self.selected_type = None
        self.selected_name = None
        self.selected_item = None
        self.selected_item_category = None
        self.category_page = 0
        self.item_page = 0
        self.refresh_components()

    async def check_owner(self, interaction):
        if str(interaction.user.id) == self.owner_user_id:
            return True
        await interaction.response.send_message(
            "これはきみの記憶編集画面じゃないみたい",
            ephemeral=True,
        )
        return False

    def current_entry(self):
        return ensure_memory_entry(self.owner_user_id)

    def category_targets(self):
        return list(MEMORY_EDIT_GROUPS)

    def current_item_entries(self):
        if self.selected_type != "group" or not self.selected_name:
            return []
        entry = self.current_entry()
        items = entry.get("items", {})
        if not isinstance(items, dict):
            return []
        entries = []
        seen = set()
        for category in ordered_memory_categories(entry):
            if memory_category_display_group(category) != self.selected_name:
                continue
            for value in normalize_item_list(items.get(category, [])):
                key = (category, value)
                if key in seen:
                    continue
                seen.add(key)
                entries.append({"category": category, "item": value})
        return entries

    def current_item_values(self):
        return [entry["item"] for entry in self.current_item_entries()]

    async def apply_direct_operations(self, interaction, operations, summary):
        try:
            result = await apply_memory_edit_operations(
                self.owner_user_id,
                operations,
                summary,
            )
        except Exception as error:
            safe_report_error(f"記憶の直接編集に失敗したよ: {error}")
            await interaction.response.send_message(
                "……記憶を変更できなかったみたい",
                ephemeral=True,
            )
            return

        if result.get("conflicts"):
            await interaction.response.send_message(
                "編集中に対象の記憶が変わっていたから、変更しなかったよ。"
                "もう一度 /memory edit から開き直してね",
                ephemeral=True,
            )
            return
        if result.get("errors"):
            await interaction.response.send_message(
                "安全に変更できなかったよ。\n"
                + "\n".join(f"・{error}" for error in result["errors"][:5]),
                ephemeral=True,
            )
            return

        changes = result.get("changes", [])
        if not changes:
            await interaction.response.send_message(
                "変更する内容はなかったみたい",
                ephemeral=True,
            )
            return

        markers = set()
        for change in changes:
            operation_type = change.get("type")
            if operation_type == "add_item":
                markers.add("📌")
            elif operation_type == "delete_item":
                markers.add("🗑️")
            elif operation_type in ("rewrite_item", "set_slot", "delete_slot"):
                markers.add("📝")
        marker = "".join(
            emoji for emoji in ("📌", "🗑️", "📝") if emoji in markers
        ) or "✅"
        action = describe_memory_operation(changes[0])
        self.refresh_components()
        content = (
            f"{marker} {discord.utils.escape_mentions(action)}\n"
            "戻すなら /memory undo\n\n"
            f"{self.render()}"
        )
        await interaction.response.edit_message(
            content=content[:DISCORD_LIMIT],
            view=self,
        )

    def refresh_components(self):
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)

        targets = self.category_targets()
        page_size = 24
        max_category_page = max(0, (len(targets) - 1) // page_size)
        self.category_page = min(self.category_page, max_category_page)
        start = self.category_page * page_size
        page_targets = targets[start:start + page_size]
        entry = self.current_entry()
        options = []
        for target_type, target_name in page_targets:
            if target_type == "slot":
                label = memory_slot_label(target_name)
                has_value = bool(entry.get("slots", {}).get(target_name))
                description = "設定済み" if has_value else "未設定"
            else:
                label = target_name
                previous_type = self.selected_type
                previous_name = self.selected_name
                self.selected_type = target_type
                self.selected_name = target_name
                count = len(self.current_item_entries())
                self.selected_type = previous_type
                self.selected_name = previous_name
                description = f"{count}件"
            options.append(discord.SelectOption(
                label=label[:100],
                value=f"{target_type}:{target_name}",
                description=description[:100],
                default=(
                    self.selected_type == target_type
                    and self.selected_name == target_name
                ),
            ))
        if options:
            self.add_item(MemoryCategorySelect(self, options))

        item_entries = self.current_item_entries()
        values = [entry["item"] for entry in item_entries]
        max_item_page = max(
            0,
            (len(values) - 1) // MEMORY_ITEM_PAGE_SIZE,
        )
        self.item_page = min(self.item_page, max_item_page)
        item_start = self.item_page * MEMORY_ITEM_PAGE_SIZE
        item_page_entries = item_entries[
            item_start:item_start + MEMORY_ITEM_PAGE_SIZE
        ]
        item_page_values = [entry["item"] for entry in item_page_entries]
        selected_item_visible = any(
            self.selected_item == entry["item"]
            and self.selected_item_category == entry["category"]
            for entry in item_page_entries
        )
        if self.selected_item and not selected_item_visible:
            self.selected_item = None
            self.selected_item_category = None
        if item_page_values:
            self.add_item(
                MemoryItemSelect(self, item_page_entries, item_start)
            )

        slot_value = (
            entry.get("slots", {}).get(self.selected_name)
            if self.selected_type == "slot"
            else None
        )
        self.add_button.disabled = self.selected_type is None or bool(slot_value)
        self.edit_button.disabled = not (
            (self.selected_type == "slot" and slot_value)
            or (
                self.selected_type == "group"
                and selected_item_visible
            )
        )
        self.delete_button.disabled = self.edit_button.disabled
        self.back_button.disabled = self.selected_type is None
        active_page = self.item_page if self.selected_type else self.category_page
        max_page = max_item_page if self.selected_type else max_category_page
        self.previous_button.disabled = active_page <= 0
        self.next_button.disabled = active_page >= max_page

    def render(self):
        entry = self.current_entry()
        if self.selected_type is None:
            lines = [
                "🗂️ 編集する記憶の種類を選んでね",
                "",
                "種類:",
                "・呼び名：1件だけの名前",
                "・覚えていること：事実、関心、作業、好きなもの",
                "・話し方・扱い方：返答態度、避けること、接し方",
            ]
            current_lines = []
            for target_type, target_name in self.category_targets():
                if target_type == "slot":
                    value = entry.get("slots", {}).get(target_name)
                    if value:
                        current_lines.append(
                            f"・{memory_slot_label(target_name)}: {value}"
                        )
                else:
                    previous_type = self.selected_type
                    previous_name = self.selected_name
                    self.selected_type = target_type
                    self.selected_name = target_name
                    count = len(self.current_item_entries())
                    self.selected_type = previous_type
                    self.selected_name = previous_name
                    if count:
                        current_lines.append(f"・{target_name}：{count}件")
            if current_lines:
                lines.extend(["", "現在:", *current_lines])
            return "\n".join(lines)[:DISCORD_LIMIT]

        if self.selected_type == "slot":
            value = entry.get("slots", {}).get(self.selected_name)
            return (
                f"🗂️ {memory_slot_label(self.selected_name)}\n"
                f"{value if value else '（未設定）'}"
            )

        values = self.current_item_values()
        start = self.item_page * MEMORY_ITEM_PAGE_SIZE
        page_values = values[start:start + MEMORY_ITEM_PAGE_SIZE]
        lines = [
            f"🗂️ {self.selected_name}",
            f"{len(values)}件",
        ]
        if self.selected_item:
            lines.extend(["", f"選択中: {self.selected_item}", ""])
        lines.extend(
            (
                f"・{start + index + 1}. {value}（選択中）"
                if value == self.selected_item
                else f"・{start + index + 1}. {value}"
            )
            for index, value in enumerate(page_values)
        )
        if not page_values:
            lines.append("（まだ項目がないよ）")
        return "\n".join(lines)[:DISCORD_LIMIT]

    @discord.ui.button(label="追加", style=discord.ButtonStyle.success, row=2)
    async def add_button(self, interaction, button):
        if not await self.check_owner(interaction):
            return
        await interaction.response.send_modal(MemoryItemModal(self, "add"))

    @discord.ui.button(label="編集", style=discord.ButtonStyle.primary, row=2)
    async def edit_button(self, interaction, button):
        if not await self.check_owner(interaction):
            return
        await interaction.response.send_modal(MemoryItemModal(self, "edit"))

    @discord.ui.button(label="削除", style=discord.ButtonStyle.danger, row=2)
    async def delete_button(self, interaction, button):
        if not await self.check_owner(interaction):
            return
        entry = self.current_entry()
        if self.selected_type == "slot":
            raw_operation = {
                "type": "delete_slot",
                "slot": self.selected_name,
            }
        else:
            category = (
                self.selected_item_category
                or MEMORY_EDIT_GROUP_DEFAULT_CATEGORY.get(
                    self.selected_name,
                    "覚え書き",
                )
            )
            raw_operation = {
                "type": "delete_item",
                "category": category,
                "item": self.selected_item,
            }
        operations, errors = prepare_memory_edit_operations(
            [raw_operation],
            entry,
        )
        if errors:
            await interaction.response.send_message(
                "安全に削除案を作れなかったよ。\n"
                + "\n".join(f"・{error}" for error in errors[:5]),
                ephemeral=True,
            )
            return
        summary = describe_memory_operation(operations[0])
        self.selected_item = None
        self.selected_item_category = None
        await self.apply_direct_operations(interaction, operations, summary)

    @discord.ui.button(label="前へ", style=discord.ButtonStyle.secondary, row=3)
    async def previous_button(self, interaction, button):
        if not await self.check_owner(interaction):
            return
        if self.selected_type:
            self.item_page = max(0, self.item_page - 1)
            self.selected_item = None
            self.selected_item_category = None
        else:
            self.category_page = max(0, self.category_page - 1)
        self.refresh_components()
        await interaction.response.edit_message(
            content=self.render(),
            view=self,
        )

    @discord.ui.button(label="次へ", style=discord.ButtonStyle.secondary, row=3)
    async def next_button(self, interaction, button):
        if not await self.check_owner(interaction):
            return
        if self.selected_type:
            self.item_page += 1
            self.selected_item = None
            self.selected_item_category = None
        else:
            self.category_page += 1
        self.refresh_components()
        await interaction.response.edit_message(
            content=self.render(),
            view=self,
        )

    @discord.ui.button(label="戻る", style=discord.ButtonStyle.secondary, row=3)
    async def back_button(self, interaction, button):
        if not await self.check_owner(interaction):
            return
        self.selected_type = None
        self.selected_name = None
        self.selected_item = None
        self.selected_item_category = None
        self.item_page = 0
        self.refresh_components()
        await interaction.response.edit_message(
            content=self.render(),
            view=self,
        )

@memory_group.command(
    name="edit",
    description="記憶一覧を開くか、自然な言葉で変更案を作ります",
)
@discord.app_commands.describe(
    instruction="記憶をどう変更したいか。省略すると一覧を開きます",
)
async def memory_edit(
    interaction: discord.Interaction,
    instruction: str = "",
):
    instruction = instruction.strip()
    user_id = str(interaction.user.id)
    if not instruction:
        view = MemoryEditView(user_id)
        await interaction.response.send_message(
            view.render(),
            view=view,
            ephemeral=True,
        )
        return
    if len(instruction) > 500:
        await interaction.response.send_message(
            "変更内容は500文字以内で教えてね",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    entry = ensure_memory_entry(user_id)
    try:
        proposal = await build_memory_instruction_proposal(
            instruction,
            entry,
        )
    except Exception as error:
        safe_report_error(f"記憶の変更案を作れなかったよ: {error}")
        await interaction.followup.send(
            "……変更案をうまく作れなかったみたい",
            ephemeral=True,
        )
        return
    if proposal.get("ambiguous"):
        await interaction.followup.send(
            format_ambiguous_memory_proposal(proposal),
            ephemeral=True,
        )
        return

    operations, errors = prepare_memory_edit_operations(
        proposal.get("operations"),
        entry,
    )
    if errors:
        await interaction.followup.send(
            "安全に実行できる変更案を作れなかったよ。\n"
            + "\n".join(f"・{error}" for error in errors[:5]),
            ephemeral=True,
        )
        return
    summary = str(proposal.get("summary") or instruction).strip()[:300]
    await interaction.followup.send(
        format_memory_edit_preview(summary, operations),
        view=MemoryEditConfirmView(user_id, summary, operations),
        ephemeral=True,
    )
