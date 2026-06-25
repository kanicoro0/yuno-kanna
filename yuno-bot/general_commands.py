from config import DISCORD_GUILD_ID, DISCORD_LIMIT, ENABLE_GIT_SAVE, OWNER_ID
from memory_model import (
    ensure_memory_entry,
    format_memory_flat_for_display,
    memory_has_content,
)


chat_history = {}
guild_notes = {}
persisted_reminders = {}


def configure(*, history, notes, persisted):
    global chat_history, guild_notes, persisted_reminders
    chat_history = history
    guild_notes = notes
    persisted_reminders = persisted


YUNO_GUIDE = """ゆのが使えるコマンドの一覧
・/memory show：現在の個人記憶を本人だけに表示
・/memory show_flat：現在の個人記憶をカテゴリなしで表示
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
    lines.extend(format_memory_flat_for_display(entry) or ["（まだ何も覚えていないよ）"])
    await interaction.response.send_message(
        "\n".join(lines)[:DISCORD_LIMIT],
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
