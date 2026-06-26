import discord

from config import DISCORD_LIMIT, LONGTERM_MEMORY_FILE, OWNER_ID
import memory_model
from memory_model import (
    ensure_memory_entry,
    format_memory_for_display,
    format_memory_record_detail_for_display,
    format_memory_records_for_display,
    memory_record_is_deleted,
    restore_memory_record,
)
from memory_v3_preview import build_memory_v3_preview, validate_memory_v3_preview


bot = None


def configure(*, discord_bot):
    global bot
    bot = discord_bot


async def send_long(channel, text, limit=2000):
    if not text:
        return
    for index in range(0, len(text), limit):
        await channel.send(text[index:index + limit])


def _owner_only(ctx):
    return str(ctx.author.id) == OWNER_ID


def _owner_reject_message():
    return "この操作は管理者だけが使えるよ"


def _count_v2_items(entry):
    if not isinstance(entry, dict):
        return 0
    items = entry.get("items")
    if not isinstance(items, dict):
        return 0
    total = 0
    for values in items.values():
        if isinstance(values, list):
            total += len(values)
        elif values:
            total += 1
    return total


def _record_count_summary(entry):
    counts = {"active": 0, "deleted": 0, "other": 0}
    if not isinstance(entry, dict):
        return counts
    for collection in memory_model.MEMORY_V3_COLLECTION_CATEGORY_DEFAULTS:
        records = entry.get(collection)
        if not isinstance(records, dict):
            continue
        for record in records.values():
            if not isinstance(record, dict):
                continue
            status = str(record.get("status", "active")).strip() or "active"
            if status in ("active", "deleted"):
                counts[status] += 1
            else:
                counts["other"] += 1
    return counts


def _format_memory_records_users_summary(limit=DISCORD_LIMIT):
    if not memory_model.memory_root_is_v3():
        return "🧾 memory_records users\nrecord形式の記憶ではないみたい"
    rows = []
    for user_id, entry in memory_model.memory_user_store().items():
        counts = _record_count_summary(entry)
        total = counts["active"] + counts["deleted"] + counts["other"]
        rows.append((str(user_id), counts, total))
    rows.sort(key=lambda row: (-row[2], row[0]))
    lines = [
        "🧾 memory_records users",
        f"users: {len(rows)}",
    ]
    for user_id, counts, total in rows:
        if total == 0:
            continue
        lines.append(
            f"・{user_id}: active {counts['active']} / "
            f"deleted {counts['deleted']} / other {counts['other']} / total {total}"
        )
        if len("\n".join(lines)) > limit - 80:
            lines.append("・ほかのユーザーは省略")
            break
    if len(lines) == 2:
        lines.append("recordはまだないみたい")
    return "\n".join(lines)[:limit]


def _parse_memory_records_args(owner_user_id, args):
    status_values = {"active", "deleted", "all"}
    collection_values = {"all", *memory_model.MEMORY_V3_COLLECTION_CATEGORY_DEFAULTS.keys()}
    target_user_id = str(owner_user_id)
    status = "active"
    collection = "all"
    page = 1
    args = list(args)

    if args and args[0] == "users":
        if len(args) == 1:
            return {"mode": "users"}
        return None

    if args and args[0].startswith("user:"):
        target_user_id = args.pop(0).split(":", 1)[1].strip()
        if not target_user_id:
            return None

    if args:
        if args[0] not in status_values:
            return None
        status = args.pop(0)
    if args:
        if args[0] not in collection_values:
            return None
        collection = args.pop(0)
    if args:
        try:
            page = max(1, int(args.pop(0)))
        except ValueError:
            return None
    if args:
        return None
    return {
        "mode": "records",
        "target_user_id": target_user_id,
        "status": status,
        "collection": collection,
        "page": page,
    }


def _parse_memory_record_args(owner_user_id, args):
    args = list(args)
    target_user_id = str(owner_user_id)
    if args and args[0].startswith("user:"):
        target_user_id = args.pop(0).split(":", 1)[1].strip()
        if not target_user_id:
            return None
    if len(args) != 2:
        return None
    collection, record_id = args
    if collection not in memory_model.MEMORY_V3_COLLECTION_CATEGORY_DEFAULTS:
        return None
    if not record_id:
        return None
    return {
        "target_user_id": target_user_id,
        "collection": collection,
        "record_id": record_id,
    }


def _memory_records_usage():
    return (
        "使い方:\n"
        "・memory_records\n"
        "・memory_records active|deleted|all [all|memories|keywords|interaction_preferences] [page]\n"
        "・memory_records users\n"
        "・memory_records user:<user_id> [active|deleted|all] [collection] [page]"
    )


def _memory_record_usage():
    return (
        "使い方:\n"
        "・memory_record <collection> <record_id>\n"
        "・memory_record user:<user_id> <collection> <record_id>"
    )


class MemoryRecordRestoreView(discord.ui.View):
    def __init__(self, owner_user_id, target_user_id, collection, record_id):
        super().__init__(timeout=300)
        self.owner_user_id = str(owner_user_id)
        self.target_user_id = str(target_user_id)
        self.collection = str(collection)
        self.record_id = str(record_id)

    async def _check_owner(self, interaction):
        if str(interaction.user.id) == self.owner_user_id:
            return True
        await interaction.response.send_message(
            _owner_reject_message(),
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="復元", style=discord.ButtonStyle.success)
    async def restore_button(self, interaction, button):
        if not await self._check_owner(interaction):
            return
        result = await restore_memory_record(
            self.target_user_id,
            collection=self.collection,
            record_id=self.record_id,
        )
        if not result.get("restored"):
            reason = result.get("reason")
            messages = {
                "missing": "recordが見つからなかったよ",
                "not_deleted": "このrecordは削除状態ではないみたい",
                "conflict": "同じ内容のactive recordがあるから復元しなかったよ",
                "v3_read_only": "今は記憶が読み取り専用みたい",
            }
            await interaction.response.send_message(
                messages.get(reason, "復元できなかったよ"),
                ephemeral=True,
            )
            return

        lines = [
            f"target_user: {self.target_user_id}",
            *format_memory_record_detail_for_display(
                self.target_user_id,
                collection=self.collection,
                record_id=self.record_id,
                limit=DISCORD_LIMIT,
            ),
            "",
            "📝 復元したよ",
        ]
        await interaction.response.edit_message(
            content="\n".join(lines)[:DISCORD_LIMIT],
            view=None,
        )


async def revealmemory(ctx, user_id: str = None):
    if not _owner_only(ctx):
        await ctx.send("⚠️ このコマンドは管理者しか使えないみたい")
        return

    target_id = user_id or str(ctx.author.id)
    entry = ensure_memory_entry(target_id)
    member = None
    if ctx.guild is not None:
        try:
            member = ctx.guild.get_member(int(target_id))
        except (TypeError, ValueError):
            pass
    display_name = member.display_name if member is not None else f"ID:{target_id}"

    lines = [f"🔍 {display_name} の全記憶："]
    lines.extend(format_memory_for_display(entry) or ["（なし）"])
    lines.append(f"・change_log: {len(entry.get('change_log', []))}件")

    await send_long(ctx.channel, "\n".join(lines[:200]))


async def memory_records(ctx, *args):
    if not _owner_only(ctx):
        await ctx.send(_owner_reject_message())
        return
    parsed = _parse_memory_records_args(str(ctx.author.id), args)
    if not parsed:
        await ctx.send(_memory_records_usage())
        return
    if parsed["mode"] == "users":
        await ctx.send(_format_memory_records_users_summary())
        return

    target_user_id = parsed["target_user_id"]
    lines = [
        f"target_user: {target_user_id}",
        *format_memory_records_for_display(
            target_user_id,
            status=parsed["status"],
            collection=parsed["collection"],
            page=parsed["page"],
            limit=DISCORD_LIMIT,
        ),
    ]
    await send_long(ctx.channel, "\n".join(lines)[:DISCORD_LIMIT])


async def memory_record(ctx, *args):
    if not _owner_only(ctx):
        await ctx.send(_owner_reject_message())
        return
    parsed = _parse_memory_record_args(str(ctx.author.id), args)
    if not parsed:
        await ctx.send(_memory_record_usage())
        return

    target_user_id = parsed["target_user_id"]
    collection = parsed["collection"]
    record_id = parsed["record_id"]
    lines = [
        f"target_user: {target_user_id}",
        *format_memory_record_detail_for_display(
            target_user_id,
            collection=collection,
            record_id=record_id,
            limit=DISCORD_LIMIT,
        ),
    ]
    view = None
    if memory_record_is_deleted(
        target_user_id,
        collection=collection,
        record_id=record_id,
    ):
        view = MemoryRecordRestoreView(
            str(ctx.author.id),
            target_user_id,
            collection,
            record_id,
        )
    await ctx.send("\n".join(lines)[:DISCORD_LIMIT], view=view)


async def memory_migration_plan_v3(ctx):
    """Owner-only dry-run plan for migrating all VPS memory data to v3."""
    if not _owner_only(ctx):
        await ctx.send("⚠️ このコマンドは管理者しか使えないみたい")
        return

    total_users = 0
    ok_users = 0
    ng_users = 0
    empty_users = 0
    total_slots = 0
    total_v2_items = 0
    total_memories = 0
    total_keywords = 0
    total_interaction_preferences = 0
    total_records = 0
    error_lines = []
    warning_lines = []

    # memory_model.configure() swaps memory_model.longterm_memory at runtime.
    # Do not import longterm_memory directly, or this command may see the initial empty dict.
    memory_store = memory_model.longterm_memory
    user_ids = sorted(str(user_id) for user_id in memory_store.keys())
    for user_id in user_ids:
        entry = ensure_memory_entry(user_id)
        total_users += 1
        preview = build_memory_v3_preview(entry)
        validation = validate_memory_v3_preview(preview)
        counts = validation.get("counts", {}) if isinstance(validation, dict) else {}
        total_slots += counts.get("slots", 0)
        total_memories += counts.get("memories", 0)
        total_keywords += counts.get("keywords", 0)
        total_interaction_preferences += counts.get("interaction_preferences", 0)
        total_records += counts.get("total_records", 0)
        total_v2_items += _count_v2_items(entry)

        if counts.get("total_records", 0) == 0 and counts.get("slots", 0) == 0:
            empty_users += 1

        if validation.get("ok"):
            ok_users += 1
        else:
            ng_users += 1
            for error in validation.get("errors", [])[:3]:
                error_lines.append(f"・{user_id}: {error}")

        for warning in validation.get("warnings", [])[:2]:
            warning_lines.append(f"・{user_id}: {warning}")

    lines = [
        "🧪 memory migration plan v3 / dry run",
        "VPS上の longterm_memory.json 全体を対象に確認したよ",
        "保存形式はまだ変更していないよ",
        "",
        "source",
        f"・source_file: {LONGTERM_MEMORY_FILE}",
        "・source_schema: v2",
        "・target_schema: v3",
        "",
        "users",
        f"・total_users: {total_users}",
        f"・ok_users: {ok_users}",
        f"・ng_users: {ng_users}",
        f"・empty_users: {empty_users}",
        "",
        "records",
        f"・v2_items_raw: {total_v2_items}",
        f"・slots: {total_slots}",
        f"・memories: {total_memories}",
        f"・keywords: {total_keywords}",
        f"・interaction_preferences: {total_interaction_preferences}",
        f"・total_v3_records: {total_records}",
        "",
        "planned files",
        "・backup: longterm_memory.v2.backup.<timestamp>.json",
        "・preview: longterm_memory.v3.preview.<timestamp>.json",
        "",
        "next",
        "・このコマンドは書き換えない",
        "・次に backup/export 実ファイル作成へ進める",
    ]

    if error_lines:
        lines.append("")
        lines.append("errors")
        lines.extend(error_lines[:20])
        if len(error_lines) > 20:
            lines.append(f"・ほか{len(error_lines) - 20}件")

    if warning_lines:
        lines.append("")
        lines.append("warnings")
        lines.extend(warning_lines[:20])
        if len(warning_lines) > 20:
            lines.append(f"・ほか{len(warning_lines) - 20}件")

    await send_long(ctx.channel, "\n".join(lines))


async def sleep(ctx):
    if not _owner_only(ctx):
        await ctx.send("⚠️ このコマンドは管理者しか使えないみたい")
        return
    await ctx.send("……おやすみ")
    print(f"🌙 {ctx.author.display_name} によって終了されました")
    await bot.close()
