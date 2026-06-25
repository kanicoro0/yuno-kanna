from config import LONGTERM_MEMORY_FILE, OWNER_ID
import memory_model
from memory_model import ensure_memory_entry, format_memory_for_display
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
