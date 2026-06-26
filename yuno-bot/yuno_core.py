import asyncio

import discord

import auto_reply
import conversation
import general_commands
import memory_model
import memory_ui
import owner_tools
import reminders
import server_memory
from config import (
    CHAT_HISTORY_FILE,
    AUTO_REPLY_SETTINGS_FILE,
    DISCORD_GUILD_ID,
    GUILD_NOTES_FILE,
    LOG_CHANNEL_ID,
    LONGTERM_MEMORY_FILE,
    REMINDERS_FILE,
)
from storage import (
    load_json_file,
    save_to_git_async as storage_save_to_git_async,
    write_json_async,
)


bot = None
modules_configured = False
chat_history = {}
guild_notes = {}
longterm_memory = {}
inner_log = {}
reminder_tasks = {}
persisted_reminders = {}
auto_reply_settings = {}
usage_log = {}
memory_lock = asyncio.Lock()


async def report_error(error_text):
    channel = bot.get_channel(LOG_CHANNEL_ID) if bot else None
    if channel:
        await channel.send(f"⚠️ エラー:\n```{error_text}```")


def safe_report_error(error_text):
    print(f"⚠️ {error_text}")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(report_error(error_text))
        else:
            loop.run_until_complete(report_error(error_text))
    except Exception as loop_error:
        print("⚠️ エラーログ送信に失敗:", loop_error)


async def save_to_git_async(commit_message):
    await storage_save_to_git_async(commit_message, safe_report_error)


async def save_guild_notes():
    try:
        await write_json_async(GUILD_NOTES_FILE, guild_notes)
        await save_to_git_async("update guild notes")
    except Exception as error:
        safe_report_error(f"サーバーメモの保存に失敗したよ: {error}")


def _load_json_mapping(path, target):
    loaded = load_json_file(path)
    target.clear()
    if isinstance(loaded, dict):
        target.update(loaded)


def _log_memory_store_shape():
    schema_version = longterm_memory.get("schema_version")
    users = longterm_memory.get("users")
    user_count = len(users) if isinstance(users, dict) else 0
    print(
        "Longterm memory loaded: "
        f"path={LONGTERM_MEMORY_FILE} "
        f"schema_version={schema_version} "
        f"users={user_count}"
    )


def configure_modules(discord_bot):
    global bot, modules_configured
    if modules_configured and bot is discord_bot:
        return
    bot = discord_bot
    memory_model.configure(
        memory_store=longterm_memory,
        lock=memory_lock,
        file_path=LONGTERM_MEMORY_FILE,
        write_json=write_json_async,
        save_to_git=save_to_git_async,
    )
    memory_ui.configure(error_reporter=safe_report_error)
    reminders.configure(
        discord_bot=discord_bot,
        tasks=reminder_tasks,
        persisted=persisted_reminders,
        file_path=REMINDERS_FILE,
        write_json=write_json_async,
        error_reporter=safe_report_error,
    )
    auto_reply.configure(
        settings_store=auto_reply_settings,
        file_path=AUTO_REPLY_SETTINGS_FILE,
        write_json=write_json_async,
        error_reporter=safe_report_error,
    )
    server_memory.configure(notes=guild_notes, save_notes=save_guild_notes)
    conversation.configure(
        discord_bot=discord_bot,
        history=chat_history,
        notes=guild_notes,
        save_notes=save_guild_notes,
        inner=inner_log,
        usage=usage_log,
        error_reporter=safe_report_error,
    )
    general_commands.configure(
        history=chat_history,
        notes=guild_notes,
        persisted=persisted_reminders,
    )
    owner_tools.configure(discord_bot=discord_bot)
    modules_configured = True


async def sync_slash_commands():
    """Slash command sync policy for multi-server operation.

    The bot is used in multiple servers, so the normal command source should be
    global commands.  If DISCORD_GUILD_ID is set, treat it only as a one-time /
    temporary cleanup target for stale guild commands that may duplicate the
    global commands in that server.
    """
    if DISCORD_GUILD_ID:
        guild = discord.Object(id=DISCORD_GUILD_ID)
        bot.tree.clear_commands(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"Stale guild slash commands cleared from {DISCORD_GUILD_ID}")

    await bot.tree.sync()
    print("Slash commands synced globally")


async def setup_hook():
    _load_json_mapping(CHAT_HISTORY_FILE, chat_history)
    _load_json_mapping(GUILD_NOTES_FILE, guild_notes)
    _load_json_mapping(LONGTERM_MEMORY_FILE, longterm_memory)
    _log_memory_store_shape()
    _load_json_mapping(REMINDERS_FILE, persisted_reminders)
    _load_json_mapping(AUTO_REPLY_SETTINGS_FILE, auto_reply_settings)
    await reminders.restore_reminders()
    await save_to_git_async("起動時保存")
    try:
        await sync_slash_commands()
    except Exception as error:
        safe_report_error(f"Slash commandの同期に失敗: {error}")


async def on_ready():
    await auto_reply.apply_sleep_presence(bot)
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send("☀️ ゆの、目が覚めた")
    print("✅ 起動完了")


def setup_commands(discord_bot):
    configure_modules(discord_bot)
    discord_bot.command(name="revealmemory", hidden=True)(owner_tools.revealmemory)
    discord_bot.command(name="memory_records", hidden=True)(owner_tools.memory_records)
    discord_bot.command(name="memory_record", hidden=True)(owner_tools.memory_record)
    discord_bot.command(name="sleep", hidden=True)(owner_tools.sleep)
    discord_bot.command(name="wake", hidden=True)(owner_tools.wake)
    discord_bot.tree.add_command(auto_reply.autorespond_group)
    discord_bot.tree.add_command(memory_ui.memory_group)
    discord_bot.tree.add_command(server_memory.servermemory_group)
    discord_bot.tree.command(
        name="remind",
        description="指定した時間にリマインドします",
    )(reminders.slash_remind)
    discord_bot.tree.command(
        name="cancelremind",
        description="設定中のリマインドをキャンセルします",
    )(reminders.slash_cancelremind)
    discord_bot.tree.command(
        name="reminders",
        description="設定中のリマインドを本人だけに表示します",
    )(reminders.slash_reminders)
    discord_bot.tree.command(
        name="guide",
        description="ゆのが使えるコマンドを表示します",
    )(general_commands.slash_guide)
    discord_bot.tree.command(
        name="status",
        description="自分に関係する保存状態を確認します",
    )(general_commands.slash_status)


def setup_events(discord_bot):
    configure_modules(discord_bot)
    for event_handler in (setup_hook, on_ready, conversation.on_message):
        discord_bot.event(event_handler)
