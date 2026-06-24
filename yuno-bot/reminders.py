import asyncio
from datetime import datetime, timedelta

import discord


bot = None
reminder_tasks = {}
persisted_reminders = {}
reminders_file = None
write_json_async = None
safe_report_error = print


def configure(*, discord_bot, tasks, persisted, file_path, write_json, error_reporter):
    global bot, reminder_tasks, persisted_reminders, reminders_file
    global write_json_async, safe_report_error
    bot = discord_bot
    reminder_tasks = tasks
    persisted_reminders = persisted
    reminders_file = file_path
    write_json_async = write_json
    safe_report_error = error_reporter


def parse_reminder_time(time_text: str, now=None):
    now = now or datetime.now()
    time_text = time_text.strip()
    if not time_text:
        raise ValueError("format")

    if ":" in time_text:
        try:
            target_time = datetime.strptime(time_text, "%H:%M").replace(
                year=now.year,
                month=now.month,
                day=now.day,
            )
        except ValueError as error:
            raise ValueError("format") from error
        if target_time < now:
            target_time += timedelta(days=1)
        return int((target_time - now).total_seconds()), target_time.strftime("%H:%M")

    try:
        minutes = float(time_text)
    except ValueError as error:
        raise ValueError("format") from error
    if minutes < 0.1 or minutes > 1440:
        raise ValueError("range")

    delay_seconds = int(minutes * 60)
    mm, ss = divmod(delay_seconds, 60)
    if mm == 0:
        label = f"{ss}秒後"
    elif ss == 0:
        label = f"{mm}分後"
    else:
        label = f"{mm}分{ss}秒後"
    return delay_seconds, label


async def deliver_reminder(user_id, channel_id, text):
    channel = None
    if channel_id is not None:
        try:
            resolved_channel_id = int(channel_id)
            channel = bot.get_channel(resolved_channel_id)
            if channel is None:
                channel = await bot.fetch_channel(resolved_channel_id)
        except Exception as error:
            safe_report_error(f"リマインダーのチャンネル取得に失敗: {error}")
    if channel:
        mention = f"<@{user_id}>"
        await channel.send(f"{mention} {text}" if text else f"{mention}、時間だよ")


async def _run_reminder(user_id, channel_id, text, delay_seconds):
    await asyncio.sleep(delay_seconds)
    try:
        await deliver_reminder(user_id, channel_id, text)
    finally:
        persisted_reminders.pop(str(user_id), None)
        await write_json_async(reminders_file, persisted_reminders)


def schedule_reminder(user_id, channel_id, text, delay_seconds):
    resolved_user_id = int(user_id)
    reminder_tasks[resolved_user_id] = asyncio.create_task(
        _run_reminder(user_id, channel_id, text, delay_seconds)
    )


async def restore_reminders():
    now = datetime.now()
    reminders_changed = False
    for user_id, reminder in list(persisted_reminders.items()):
        try:
            due = datetime.fromisoformat(reminder.get("due_at"))
        except (AttributeError, TypeError, ValueError):
            continue
        if due <= now:
            persisted_reminders.pop(user_id, None)
            reminders_changed = True
            continue
        schedule_reminder(
            user_id,
            reminder.get("channel_id"),
            reminder.get("text"),
            (due - now).total_seconds(),
        )
    if reminders_changed:
        await write_json_async(reminders_file, persisted_reminders)

@discord.app_commands.describe(
    time="分数、または HH:MM",
    message="時間になったときのメッセージ（省略可）",
)
async def slash_remind(
    interaction: discord.Interaction,
    time: str,
    message: str = None,
):
    user_id = interaction.user.id
    if user_id in reminder_tasks and not reminder_tasks[user_id].done():
        await interaction.response.send_message(
            "⚠️ すでにリマインドが設定されてるみたい。`/cancelremind` でキャンセルしよう",
            ephemeral=True,
        )
        return

    if message is not None and len(message) > 500:
        await interaction.response.send_message(
            "⚠️ リマインドのメッセージは500文字以内でお願い",
            ephemeral=True,
        )
        return

    try:
        delay_seconds, label = parse_reminder_time(time)
    except ValueError as error:
        if str(error) == "range":
            error_message = "⚠️ リマインド時間は0.1〜1440分の間で指定しよう"
        else:
            error_message = "⚠️ `MM`分後または `HH:MM` の形式で指定しよう"
        await interaction.response.send_message(
            error_message,
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    channel_id = interaction.channel_id
    persisted_reminders[str(user_id)] = {
        "channel_id": channel_id,
        "text": message,
        "due_at": (datetime.now() + timedelta(seconds=delay_seconds)).isoformat(),
    }
    await write_json_async(reminders_file, persisted_reminders)
    await interaction.followup.send(
        f"……うん、{label}に声を届ける",
        ephemeral=True,
    )

    schedule_reminder(user_id, channel_id, message, delay_seconds)

async def slash_cancelremind(interaction: discord.Interaction):
    user_id = interaction.user.id
    task = reminder_tasks.get(user_id)
    has_task = bool(task and not task.done())
    has_persisted = str(user_id) in persisted_reminders
    if not has_task and not has_persisted:
        await interaction.response.send_message(
            "⚠️ 今はキャンセルできるリマインドがないみたい",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    task = reminder_tasks.pop(user_id, None)
    if task and not task.done():
        task.cancel()

    if str(user_id) in persisted_reminders:
        persisted_reminders.pop(str(user_id), None)
        await write_json_async(reminders_file, persisted_reminders)
    await interaction.followup.send(
        "🔕 リマインドをキャンセルしたよ",
        ephemeral=True,
    )

async def slash_reminders(interaction: discord.Interaction):
    reminder = persisted_reminders.get(str(interaction.user.id))
    if not isinstance(reminder, dict):
        await interaction.response.send_message(
            "今は設定中のリマインドはないみたい",
            ephemeral=True,
        )
        return

    due_at_text = reminder.get("due_at", "")
    try:
        due_at = datetime.fromisoformat(due_at_text)
        remaining_seconds = max(0, int((due_at - datetime.now()).total_seconds()))
        days, remainder = divmod(remaining_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts = []
        if days:
            parts.append(f"{days}日")
        if hours:
            parts.append(f"{hours}時間")
        if minutes:
            parts.append(f"{minutes}分")
        if seconds or not parts:
            parts.append(f"{seconds}秒")
        remaining_text = "".join(parts)
    except (TypeError, ValueError):
        due_at_text = "（日時を読み取れない）"
        remaining_text = "不明"

    message_text = reminder.get("text") or "（なし）"
    channel_id = reminder.get("channel_id")
    channel_text = f"<#{channel_id}>" if channel_id else "不明"
    await interaction.response.send_message(
        "⏳ 設定中のリマインド：\n"
        f"・実行予定: {due_at_text}\n"
        f"・残り時間: {remaining_text}\n"
        f"・メッセージ: {message_text}\n"
        f"・通知先: {channel_text}",
        ephemeral=True,
    )
