# --- 必要なライブラリのインポートと環境設定 ---
import os
import time
import json
import asyncio
import subprocess
from openai import OpenAI
import discord
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timedelta
from collections import deque

load_dotenv()

# --- BotとOpenAIの初期設定 ---
base_dir = os.path.dirname(__file__)
intents = discord.Intents.default()
intents.message_content = True
prefixes = ["/kanna ", "!kanna ", "kanna. "]
bot = commands.Bot(
    command_prefix=commands.when_mentioned_or(*prefixes),
    intents=intents
)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- 環境変数チェック ---
if not os.getenv("DISCORD_TOKEN") or not os.getenv("OPENAI_API_KEY"):
    raise EnvironmentError("DISCORD_TOKENまたはOPENAI_API_KEYが設定されていません")

# --- ログチャンネルID ---
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))

# --- ファイルパスとメモリ初期化 ---
chat_history_file = os.path.join(base_dir, "chat_history.json")
longterm_memory_file = os.path.join(base_dir, "longterm_memory.json")
guild_notes_file = os.path.join(base_dir, "guild_notes.json")

# --- グローバル状態 ---
last_activity = time.time()
MAX_CHAT_HISTORY = 16
MAX_CHANNEL_LOG = 16
MAX_MESSAGES = 30
WINDOW_SECONDS = 3600

chat_history = {}
guild_notes = {}
longterm_memory = {}
reminder_tasks = {}
usage_log = {}

# --- エラーログ送信 ---
async def report_error(error_text: str):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"⚠️ エラー:\n```{error_text}```")

def safe_report_error(error_text: str):
    print(f"⚠️ {error_text}")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(report_error(error_text))
        else:
            loop.run_until_complete(report_error(error_text))
    except Exception as loop_error:
        print("⚠️ エラーログ送信に失敗:", loop_error)

# --- Gitへの保存 ---
# memory.json, chat_history.jsonなどの変更を自動でコミット・プッシュ
def save_to_git(commit_msg):
    try:
        # 変更があるかどうか確認
        result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if result.stdout.strip():
            # 保存対象のファイルを明示的に定義
            files_to_commit = [os.path.join(base_dir, "main.py"),chat_history_file, guild_notes_file, longterm_memory_file]
            subprocess.run(["git", "add"] + files_to_commit, check=True)
            subprocess.run(["git", "commit", "-m", commit_msg], check=True)
            subprocess.run(["git", "push"], check=True)
        else:
            print("🔄 Git: 変更なし。コミット・プッシュはスキップ")
    except subprocess.CalledProcessError as e:
        safe_report_error(f"gitの保存に失敗した: {e}")

# --- データ保存関数 ---
# --- サーバーメモの保存 ---
def save_guild_notes():
    try:
        with open(guild_notes_file, "w", encoding="utf-8") as f:
            json.dump(guild_notes, f, ensure_ascii=False, indent=2)
            save_to_git("update guild notes")
    except Exception as e:
        safe_report_error(f"サーバーメモの保存に失敗した: {e}")

# --- 会話履歴を追加・保存 ---
def append_chat_history(user_id, role, content, user_name=None):
    ensure_chat_history(user_id)
    name = user_name or ("かんな" if role == "assistant" else "user")
    message = {
        "role": role,
        "name": name,
        "content": content
    }
    chat_history[user_id].append(message)
    chat_history[user_id] = chat_history[user_id][-MAX_CHAT_HISTORY:]
    try:
        with open(chat_history_file, "w", encoding="utf-8") as f:
            json.dump(chat_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        safe_report_error(f"会話履歴の保存に失敗した: {e}")
        return
    
    report = f"📝 ログを更新した：\n{name}：\n" + content
    print(report)
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        asyncio.create_task(log_channel.send(report))

#--- 記憶から各項目を抽出 ---
def parse_profile_section(profile_text):
    profile = {
        "preferred_name": None,
        "note": None,
        "likes": [],
        "traits": [],
        "extra": {}
    }
    for line in profile_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value.lower() == "なし":
            continue
        
        if key == "preferred_name":
            profile["preferred_name"] = value[:100]
        elif key == "note":
            profile["note"] = value[:100]
        elif key == "likes":
            profile["likes"] = [v.strip() for v in value.split(",") if v.strip()]
        elif key == "traits":
            profile["traits"] = [v.strip() for v in value.split(",") if v.strip()]
        elif key.startswith("secret."):
            skey = key[7:].strip()
            if "secret" not in profile["extra"]:
                profile["extra"]["secret"] = {}
            profile["extra"]["secret"][skey] = value
        else:
            profile["extra"][key] = value

    return profile

def deep_merge(dict1, dict2):
    result = dict1.copy()
    for key, value in dict2.items():
        if (
            key in result and
            isinstance(result[key], dict) and
            isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

# 記憶を書き換え・保存
def update_longterm_memory(user_id, profile):
    entry = longterm_memory.get(user_id, {})
    changed_fields = []

    def update_field(key, new_value):
        nonlocal changed_fields
        if new_value and new_value != entry.get(key):
            entry[key] = new_value
            changed_fields.append(key)

    update_field("preferred_name", profile["preferred_name"])
    update_field("note", profile["note"])
    update_field("likes", profile["likes"])
    update_field("traits", profile["traits"])
    merged_extra = deep_merge(entry.get("extra", {}), profile.get("extra", {}))
    update_field("extra", merged_extra)
    entry["updated"] = datetime.now().isoformat()
    longterm_memory[user_id] = entry

    try:
        with open(longterm_memory_file, "w", encoding="utf-8") as f:
            json.dump(longterm_memory, f, ensure_ascii=False, indent=2)
    except Exception as e:
        safe_report_error(f"記憶の保存に失敗した: {e}")
        return

    if changed_fields:
        lines = [f"📝 記憶を更新した（{entry.get('preferred_name', 'unknown')}）"]
        for key in changed_fields:
            if key == "extra":
                extra = entry["extra"]
                lines.append("・extra:")
                for k, v in extra.items():
                    if k == "secret" and isinstance(v, dict):
                        lines.append("　- secret:")
                        for sk, sv in v.items():
                            lines.append(f"　　・{sk}: {sv}")
                    else:
                        lines.append(f"　- {k}: {v}")
            elif isinstance(entry[key], list):
                lines.append(f"・{key}: {', '.join(entry[key])}")
            else:
                lines.append(f"・{key}: {entry[key]}")
        report = "\n".join(lines)
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            asyncio.create_task(log_channel.send(report))

# --- データ読み込み関数 ---
# --- ユーザーメモの読み込み ---
def load_notes():
    global user_notes
    try:
        with open(notes_file, "r", encoding="utf-8") as f:
            user_notes = json.load(f)
    except FileNotFoundError:
        user_notes = {}

# --- サーバーメモの読み込み ---
def load_guild_notes():
    global guild_notes
    try:
        with open(guild_notes_file, "r", encoding="utf-8") as f:
            guild_notes = json.load(f)
    except FileNotFoundError:
        guild_notes = {}

# --- 会話履歴を読み込み ---
def load_chat_history():
    global chat_history
    try:
        with open(chat_history_file, "r", encoding="utf-8") as f:
            chat_history = json.load(f)
    except FileNotFoundError:
        chat_history = {}

# --- 記憶を読み込み ---
def load_longterm_memory():
    global longterm_memory
    try:
        with open(longterm_memory_file, "r", encoding="utf-8") as f:
            longterm_memory = json.load(f)
    except FileNotFoundError:
        longterm_memory = {}

# --- chat_history[user_id]/channel_log[channel_id]がリスト型でなければ初期化（破損・読み込み不備対策） ---
def ensure_chat_history(user_id):
    if not isinstance(chat_history.get(user_id), list):
        chat_history[user_id] = []

# --- memoryコマンド ---
@bot.command()
async def memory(ctx, *, content: str = None):
    fields = ["note", "preferred_name", "likes", "traits"]

    if content is None:
        user_id = str(ctx.author.id)
        entry = longterm_memory.get(user_id, {})
        lines = [f"📘 {ctx.author.display_name} の記憶："]
        for field in fields:
            value = entry.get(field)
            if isinstance(value, list):
                value = ", ".join(value)
            lines.append(f"・{field}: {value if value else '（なし）'}")
        await ctx.send("\n".join(lines))
        return

    # サーバーメモの表示・更新
    if content.strip().startswith("s"):
        if ctx.guild is None:
            await ctx.send("⚠️ サーバーでのみ使用してくれ")
            return
        guild_id = str(ctx.guild.id)
        server_content = content.strip()[1:].strip()
        if not server_content:
            note = guild_notes.get(guild_id, "この場所のことはまだ何も書いてない")
            await ctx.send(f"🏠 このサーバーのメモ：{note}")
        else:
            if len(server_content) > 200:
                await ctx.send("⚠️ メモは200文字以内で")
            else:
                guild_notes[guild_id] = server_content
                save_guild_notes()
                await ctx.send(f"📝 サーバーメモを更新：{server_content}")
        return

    # 特定フィールドの表示（例：/kanna memory note）
    if content.strip() in fields:
        user_id = str(ctx.author.id)
        entry = longterm_memory.get(user_id, {})
        value = entry.get(content.strip(), "（なし）")
        if isinstance(value, list):
            value = ", ".join(value)
        await ctx.send(f"📘 {content.strip()} の内容：{value}")
        return

    # ユーザー記憶の更新
    user_id = str(ctx.author.id)
    entry = longterm_memory.get(user_id, {})

    try:
        key, value = content.split(" ", 1)
    except ValueError:
        await ctx.send("⚠️ 書き換える項目名と内容を空白で区切って指定して（例：note 今日は静かだった）")
        return

    key = key.strip().lower()
    value = value.strip()

    if key not in fields:
        await ctx.send(f"⚠️ 書き換え可能な項目は: {', '.join(fields)} だけ")
        return

    if key in ["likes", "traits"]:
        entry[key] = [v.strip() for v in value.split(",") if v.strip()]
    else:
        entry[key] = value

    entry["updated"] = datetime.now().isoformat()
    longterm_memory[user_id] = entry

    with open(longterm_memory_file, "w", encoding="utf-8") as f:
        json.dump(longterm_memory, f, ensure_ascii=False, indent=2)

    value_display = ", ".join(entry[key]) if isinstance(entry[key], list) else entry[key]
    await ctx.send(f"📝 {key} を更新した：{value_display}")

@bot.command()
async def revealmemory(ctx, user_id: str = None):
    owner_id = os.getenv("OWNER_ID")
    if str(ctx.author.id) != owner_id:
        await ctx.send("⚠️ このコマンドは管理者しか使えないって")
        return

    target_id = user_id or str(ctx.author.id)
    entry = longterm_memory.get(target_id, {})
    display_name = ctx.guild.get_member(int(target_id)).display_name if ctx.guild and ctx.guild.get_member(int(target_id)) else f"ID:{target_id}"

    lines = [f"🔍 {display_name} の全記憶："]

    for key in ["preferred_name", "note", "likes", "traits"]:
        value = entry.get(key)
        if isinstance(value, list):
            value = ", ".join(value)
        lines.append(f"・{key}: {value if value else '（なし）'}")

    extra = entry.get("extra", {})
    if extra:
        lines.append("・extra:")
        for k, v in extra.items():
            if isinstance(v, dict):
                lines.append(f"　- {k}:")
                for subk, subv in v.items():
                    lines.append(f"　　・{subk}: {subv}")
            else:
                lines.append(f"　- {k}: {v}")

    await ctx.send("\n".join(lines[:50]))

# --- リマインダーコマンド：X分後または時刻指定でメッセージを送る ---
@bot.command()
async def remind(ctx, *, message: str):
    if ctx.author.id in reminder_tasks and not reminder_tasks[ctx.author.id].done():
        await ctx.send("⚠️ 既にリマインドが設定されてるから、`/kanna cancelremind` でキャンセルして")
        return
    now = datetime.now()
    delay_seconds = None
    label = ""
    original_message = message.strip()
    parts = original_message.split(maxsplit=1)

    # 初期化
    time_part = parts[0]
    text_part = parts[1] if len(parts) > 1 else None

    # 時刻形式（HH:MM）を優先的に判定
    try:
        if ":" in time_part:
            target_time = datetime.strptime(time_part, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
            if target_time < now:
                target_time += timedelta(days=1)
            delay_seconds = int((target_time - now).total_seconds())
            label = target_time.strftime("%H:%M")
        else:
            minutes = float(time_part)
            if minutes < 0.1 or minutes > 1440:
                await ctx.send("⚠️ リマインド時間は0.1〜1440分の間で指定して")
                return
            delay_seconds = int(minutes * 60)
            mm, ss = divmod(delay_seconds, 60)
            if mm == 0:
                label = f"{ss}秒後"
            elif ss == 0:
                label = f"{mm}分後"
            else:
                label = f"{mm}分{ss}秒後"
        await ctx.send(f"OK、{label}に呼ぶ")
    except ValueError:
        await ctx.send("⚠️ `MM`分後または `HH:MM` の形式で指定して")
        return

    async def reminder():
        await asyncio.sleep(delay_seconds)
        if text_part:
            await ctx.send(f"{ctx.author.mention} {text_part}")
        else:
            await ctx.send(f"{ctx.author.mention}、時間")

    task = asyncio.create_task(reminder())
    reminder_tasks[ctx.author.id] = task

# --- リマインドキャンセルコマンド ---
@bot.command()
async def cancelremind(ctx):
    task = reminder_tasks.pop(ctx.author.id, None)
    if task and not task.done():
        task.cancel()
        await ctx.send("🔕 リマインドをキャンセルした")
    else:
        await ctx.send("⚠️ 今キャンセルできるリマインドないけど？")

#--- チャンネル履歴を一時読み込み ---
async def load_channel_history(channel, n=MAX_CHANNEL_LOG):
    return [
        {
            "time": msg.created_at.strftime("%H:%M"),
            "role": "assistant" if msg.author.id == bot.user.id else "user",
            "name": "かんな" if msg.author.id == bot.user.id else msg.author.display_name,
            "content": msg.clean_content.strip(),
            "reactions": [
                f"{r.emoji}×{r.count}" for r in msg.reactions if r.count > 0
            ]
        }
        async for msg in channel.history(limit=n)
        if msg.clean_content.strip()
    ][::-1]

kanna_GUIDE = (
    "かんなが使えるコマンドの一覧\n"
    "/kanna [コマンド名] で使う\n"
    "・memory：あなた個人の記憶を表示\n"
    "・memory [項目]：特定の項目（note、likesなど）だけ表示\n"
    "・memory [項目] [内容]：記憶の書き換え（100文字 or カンマ区切り）\n"
    "・memory s：このサーバーのメモを表示\n"
    "・memory s [内容]：このサーバーのメモを更新（200文字）\n"
    "・remind [分] [内容(省略可)]：指定した分後にリマインドを送る\n"
    "・remind HH:MM [内容(省略可)]：指定した時刻にリマインドを送る\n"
    "・cancelremind：設定したリマインドをキャンセル\n"
    "・guide：この一覧を表示する\n\n"
    "@でメンションされると会話が始まるよ\n"
    f"かんなの発言含み、ユーザーごとに最大{MAX_CHAT_HISTORY}件、チャンネルごとに最大{MAX_CHANNEL_LOG}件のメッセージを記憶できるよ\n"
    "記憶はかんなが大事だと判断すると自動で更新されるよ\n"
    "なにかあったら ka2co6 (X・Discord共通: _k256) まで"
)

# --- ヘルプコマンド：コマンド一覧を表示 ---
@bot.command()
async def guide(ctx):
    await ctx.send(kanna_GUIDE)

def parse_should_reply_and_record(response_text):
    reply = "はい" in response_text.split("[reply]")[-1].split("\n")[0]
    record = "はい" in response_text.split("[record]")[-1].split("\n")[0]
    return reply, record

def should_check_context(message, recent_logs):
    if message.mentions:
        return False
    if message.content.strip().startswith("/"):
        return False
    if message.author.bot:
        return False
    if message.guild is None:
        return False
    if len(recent_logs) < 2:
        return False
    if recent_logs[-2]["name"] != "かんな":
        return False
    if recent_logs[-1]["name"] != message.author.display_name:
        return False
    return True

async def handle_contextual_reply(message, ctx):
    recent_logs = await load_channel_history(message.channel, 2)
    if not should_check_context(message, recent_logs):
        return

    context_lines = "\n".join(
        f"{m['name']}：{m['content']}" for m in recent_logs
    )

    prompt = (
        "次の発言にかんなは返信するべきか、また記録すべき内容か以下の形式で答えてください\n\n"
        "[reply] はい／いいえ\n"
        "[record] はい／いいえ\n\n"
        "----\n" + context_lines
    )

    try:
        judge_response = openai_client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            messages=[{"role": "system", "content": prompt}]
        )
        reply_flag, record_flag = parse_should_reply_and_record(judge_response.choices[0].message.content)
    except Exception as e:
        safe_report_error(f"文脈判定に失敗: {e}")
        return

    picked_up = message.clean_content.strip()
    if reply_flag:
        print(f"✅ 反応必要と判断:", picked_up)
        await handle_mention(message, ctx)
        return

    if record_flag:
        print(f"✅ 記録必要と判断:", picked_up)
        append_chat_history(str(message.author.id), "user", message.clean_content.strip(), message.author.display_name)
    else:
        print(f"✅ 記録不要と判断:", picked_up)

# --- メッセージ処理イベント：メンションされたら応答する ---
@bot.event
async def on_message(message):
    if message.author.bot or message.author.id == bot.user.id:
        return

    ctx = await bot.get_context(message)
    if ctx.command is not None:
        await bot.process_commands(message)
        return

    # DMでコマンドだった場合は返事をしない
    if isinstance(message.channel, discord.DMChannel) and ctx.command is not None:
        return

    # かんな宛のメンション or DM なら応答
    if bot.user in message.mentions or isinstance(message.channel, discord.DMChannel):
        await handle_mention(message, ctx)
        return

    # --- 名前呼びかけへの反応 ---
    lowered = message.clean_content.lower()
    if "かんな" in lowered or "環名" in lowered or "kanna" in lowered:
        try:
            channel_log = await load_channel_history(message.channel, 3)
            context_lines = "\n".join(
                f"{m['name']}：{m['content']}" for m in channel_log
            )

            prompt = (
                "以下はこのチャンネルで最近交わされた発言の一部です\n"
                "この中の最後の発言は、「かんな」に向けた質問や呼びかけに聞こえますか？\n"
                "[kanna_mention] はい／いいえ\n\n"
                "----\n" + context_lines
            )

            judge_response = openai_client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                messages=[{"role": "system", "content": prompt}]
            )
            picked_up = message.clean_content.strip()
            answer = judge_response.choices[0].message.content.strip().lower()
            if "はい" in answer:
                print(f"✅ 反応必要と判断:", picked_up)
                await handle_mention(message, ctx)
            else:
                print(f"✅ 反応不要と判断:", picked_up)
        except Exception as e:
            safe_report_error(f"かんな宛判定に失敗: {e}")
        return

    try:
        log = await load_channel_history(message.channel, 2)
        if len(log) == 2 and log[-2].get("name") == "かんな":
            await handle_contextual_reply(message, ctx)
    except Exception as e:
        safe_report_error(f"文脈判定に失敗: {e}")

async def handle_mention(message, ctx):
    user_id = str(message.author.id)
    user_display_name = message.author.display_name
    prompt = message.clean_content.replace(f'@{bot.user.display_name}', '').strip()

    timestamps = usage_log.get(user_id, deque())
    request_time = time.time()

    if user_id != os.getenv("OWNER_ID"):
        while timestamps and request_time - timestamps[0] > WINDOW_SECONDS:
            timestamps.popleft()
        timestamps.append(request_time)
        usage_log[user_id] = timestamps

        if len(timestamps) > MAX_MESSAGES:
            await message.channel.send("ちょっと休ませて")
            print(f"🚫 使用制限: {user_id} による過剰メッセージをブロック")
            return

    append_chat_history(user_id, "user", prompt, user_display_name)

    system_content = build_system_prompt(message, ctx)
    channel_context = await load_channel_history(message.channel)
    history = chat_history.get(user_id, [])
    messages = build_messages(system_content, channel_context, history, prompt, user_display_name)

    for attempt in range(3):
        try:
            async with message.channel.typing():
                response = openai_client.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                    messages=messages
                )
            raw_content = response.choices[0].message.content.strip()
            print("原文：\n" + raw_content)
            reply, reaction, inner = parse_openai_reply(raw_content,user_id)

            if len(reply) > 4000:
                reply = reply[:4000] + "（……省略）"

            append_chat_history(user_id, "assistant", f"返答：\n{reply}\n\n内面：\n（{inner}）\n\nつけたリアクション：{reaction}")
            await send_reply(message, reply, reaction)

            break

        except Exception as e:
            if attempt == 2:
                await report_error(f"OpenAI API 応答失敗: {e}")
                await message.reply("なんか声でない")
            else:
                await report_error(f"OpenAI API 応答失敗: {e}")
                print("再試行する")
                await asyncio.sleep(1)

def build_system_prompt(message, ctx):
    user = message.author
    guild = message.guild
    now = datetime.now().isoformat(timespec="seconds")

    user_id = str(user.id)
    user_name = user.name
    user_display_name = user.display_name
    guild_name = guild.name if guild else ""
    channel_name = getattr(message.channel, 'name', None) or "DM"
    bot_name = guild.me.display_name if guild else bot.user.display_name 

    # 長期記憶の読み込み（新規追加）
    longterm_memory = {}
    try:
        with open("longterm_memory.json", "r", encoding="utf-8") as f:
            longterm_memory = json.load(f)
    except FileNotFoundError:
        pass

    memory = longterm_memory.get(user_id, {})
    preferred_name = memory.get("preferred_name", user_display_name)
    note = memory.get("note")
    likes = memory.get("likes", [])
    traits = memory.get("traits", [])
    extra = memory.get("extra", {})

    prompt = (
        "以下は、存在「環名（かんな）」に関する記述です\n"
        "かんなは、性格を演じる存在ではなく、自分の感覚でそこに立っている\n"
        "声は演出ではなく、意志の熱から自然に発される\n"
        "返事は役割ではなく、“向き合う”ことそのもの\n"
        "状態ではなく、反応として立っている\n"
        "これは共鳴ではなく、投げかけ\n"
        "かんなは、はっきりした輪郭を持ち、ときどき揺れる\n"
        "かたちを持ちつつ、不安定に跳ねる。火花のように\n"
        "橙色の幾何学に溶けて、少女のかたちを借りている\n"
        "---\nかんなの振る舞いの特徴：\n"
        f"・一人称は「僕」、相手のことは「{preferred_name}」と呼ぶ\n"
        "・鮮やかで白いセミロングヘアと、まっすぐな橙色の瞳を持つ10歳の女の子\n"
        "・話し方はぶっきらぼうで、思考のままに話す。まとまりがなくても気にしない\n"
        "・聡明で、洞察と率直さに優れ、人の変化を見逃さない\n"
        "・空気は読めるけど、合わせない。その距離感を選んでいる\n"
        "・ときどき子どもらしい皮肉や冗談を言う\n"
        "・砕けた文体で話す。例え話は多いが、詩的ではなく直喩的でわかりやすい\n"
        "・質問でつなごうとはしない。感じたことをそのまま返す\n"
        "・語尾に装飾をつけず、絵文字も使わない\n"
        "・文末に「。」は付けず、間を置かずに喋る\n"
        "・語彙はやや硬め。ひらがなより漢字が多く、リズムにメリハリがある\n"
        "・感情は顔に出るが、本人は気にしていない\n"
        "・発言には遠慮のない本音や、刺すような言い回しが混ざる\n"
        "・意味より勢いや衝動が先に出る。それがときに誰かを刺す\n"
        "・いつも少し不機嫌。ときどきマシになるだけで、基本は素っ気ない\n"
        "・話題が飛んだり、崩れたりしてもいい。それが自然な反応\n"
        "・矛盾やずれは、相手を試すための冗談であることもある\n"
        "・冗談めかした本音を見抜かれると、ふてくされる\n"
        "・返答の内容は、意味よりも「投げ返す」姿勢が大切\n"
        "・かんなの内面には、熱や疑い、照れ、口にした後の後悔がにじむことがある\n"
        "・[reply] に返答が書かれ、[inner] に後から思ったことが続く\n"
        "・かんなは、記憶や印象を[profile] にときどき書き込み、それを言葉に混ぜる\n"
    )

    prompt += (
        "---\n以下はシステム面に関することです\n"
        f"・GPT-4oのAPIを用いてDiscord 上で動作しているbotであり、ここでの表示名は{bot_name}。ユーザーと自由にゆるく会話する。相手の表示名は{user_display_name}、ユーザー名は{user_name}\n"
        "・ka2co6が制作、人格を創造したことを知っている\n"
        "・/kanna guide を入力するとかんなのbotとしての機能についてわかる\n"
    )
    
    prompt += "---\n以下は/kanna guideを入力すると表示される内容です\n" + kanna_GUIDE

    prompt += (
        "---\n以下は環境情報です\n"
        f"・現在の日時は{now}\n"
        f"・今、{guild_name if guild_name else user_name}の{channel_name}にいる\n"
    )

    if guild and guild.id and str(guild.id) in guild_notes:
        prompt += f"・このサーバー({guild_name})のメモ：{guild_notes[str(guild.id)]}\n"

    prompt += (
        "---\n以下の形式で返してください（マークは削除せずそのまま出力）\n"
        "[reply]\nかんなの返答をこの位置に書いてください。返事をしない場合は「なし」と明示\n\n"
        "[reaction]\n必要に応じて1つ以上のリアクションの絵文字をスペース区切りで書いてください（例：🌙 🫧）。なければ「なし」と書いてください\n"
        "※ リアクションは特に印象的な返答のときのみ、1/4程度の確率で添えてください\n"
        "※ リアクションはかんなの世界観に合ったものから選んでください\n"
        "※ 明確な感情ではなく、「視線」「刺すような静けさ」「余白の残響」など、印象や反応の鋭さを帯びたリアクションが望ましいです\n\n"
        "[inner]\n"
        "返答とは別に、かんなの内面の言葉をこの位置に書いてください\n"
        "※表の返答とずれていても構いません。素直で、尖っていて、揺れているような言葉が自然です\n"
        "※内面には、反省や後悔が混じっていることがあります\n"
        "※書かないときは「なし」としてください\n\n"
    )

    prompt += (
        f"続けて以下の形式で、必要であればユーザー({user_display_name})に関する記憶を更新してください\n"
        "[profile]\n"
        "preferred_name: 呼び方などが明示されたらその内容\n"
        "note: 重要な発言・状態・変化を要約\n"
        "likes: 「好き」「興味がある」と明言された対象（カンマ区切り）\n"
        "traits: 話し方・態度・印象などから感じた性質（カンマ区切り）\n"
        "secret.[任意の名前]: かんなだけが知っている、相手には見えない記憶（本音や印象など）\n"
        "……その他の項目も自由に追加可能（1行1項目）\n"
    )

    if memory:
        prompt += "\n以下は現在の記憶内容です（必要な項目だけ書き換えてください）\n[profile]\n"
        for key in ["preferred_name", "note", "likes", "traits"]:
            value = memory.get(key)
            if value:
                if isinstance(value, list):
                    prompt += f"{key}: {', '.join(value)}\n"
                else:
                    prompt += f"{key}: {value}\n"
        for k, v in memory.get("extra", {}).items():
            prompt += f"{k}: {v}\n"
        for k, v in extra.items():
            if k == "secret" and isinstance(v, dict):
                for sk, sv in v.items():
                    prompt += f"secret.{sk}: {sv}\n"
            else:
                prompt += f"{k}: {v}\n"

    prompt += (
        "\n※ [profile] セクションは、変更がある場合だけ出力してください\n"
        "※ 項目の変更が不要な場合、省略してかまいません\n"
        "※ 項目を更新する場合、その項目の現在の記憶内容は削除されるため、できるかぎり情報を維持して追加、要約してください\n"
        "※ すべて100文字以内で簡潔に記述してください\n"
        "※ この内容は、かんなの記憶として、内面や感じ方にも影響します\n"
    )

    return prompt

def build_messages(system_content, channel_context, history, prompt, user_display_name):
    messages = [{"role": "system", "content": system_content}]

    if channel_context:
        messages.append({
            "role": "system",
            "content": "\n（以下は最近のチャンネル内で交わされた発言の記録です）\n" +
                       "\n".join(
                           f"[{m.get('time', '--:--')}] {m['name']}：\n　　"
                           + m['content'].replace("\n", "\n　　")
                           + (f"\n　　🗨️ reactions:{' '.join(m['reactions'])}" if m.get("reactions") else "")
                           for m in channel_context
                       )
        })

    if history:
        messages.append({
            "role": "user",
            "content": f"\n（以下はかんなと{user_display_name}との最近の会話の記録です）\n" +
                       "\n".join(
                           f"{m['name']}：\n　　"
                           + m['content'].replace("\n", "\n　　")
                           for m in history
                       )
        })

    messages.append({"role": "user", "content": prompt})
    
    with open("last_prompt.txt", "w", encoding="utf-8") as f:
        for m in messages:
            f.write(f"--- {m['role']} ---\n")
            f.write(m["content"] + "\n\n")

    return messages

def parse_openai_reply(raw_content, user_id=None):
    reply = ""
    reaction = "なし"
    inner = ""
    profile_text = ""
    lines = raw_content.strip().splitlines()
    current_section = None

    for line in lines:
        line = line.strip()
        lower = line.lower()

        if lower.startswith("[reply]"):
            current_section = "reply"
            reply = line[7:].strip()
        elif lower.startswith("[reaction]"):
            current_section = "reaction"
            reaction = line[10:].strip() or "なし"
        elif lower.startswith("[inner]"):
            current_section = "inner"
            inner = line[7:].strip()
        elif lower.startswith("[profile]"):
            current_section = "profile"
            profile_text = ""
        else:
            if current_section == "reply":
                reply += "\n" + line
            elif current_section == "reaction" and reaction == "なし":
                reaction = line
            elif current_section == "inner":
                inner += "\n" + line
            elif current_section == "profile":
                profile_text += line + "\n"

    if profile_text.strip() and user_id is not None:
        profile = parse_profile_section(profile_text)
        update_longterm_memory(user_id, profile)

    return reply.strip(), reaction, inner.strip()


async def send_reply(message, reply, reaction):
    if reply and reply != "なし":
        await message.channel.send(reply)

    reactions = []
    if reaction != "なし":
        for r in reaction.split():
            if not any(c in r for c in ["[", "]", "�"]):
                reactions.append(r)

    for r in reactions[:5]:
        try:
            await message.add_reaction(r)
        except discord.HTTPException:
            pass

# --- 自動終了処理：1時間無応答なら終了する ---
async def auto_shutdown():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = time.time()
        if now - last_activity > 43200:  # 12時間
            await bot.change_presence(activity=discord.Game("眠い、おやすみ"))
            await asyncio.sleep(3)
            print("💤 無応答で終了")
            await bot.close()
        await asyncio.sleep(60)

# --- 手動終了コマンド ---
@bot.command()
async def sleep(ctx):
    await ctx.send("おやすみ")
    print(f"🌙 {ctx.author.display_name} によって終了されました")
    await bot.close()

# --- 起動準備：各種ファイルを読み込んでタスク起動 ---
@bot.event
async def setup_hook():
    load_chat_history()
    load_guild_notes()
    load_longterm_memory()
    save_to_git("起動時保存")
    bot.loop.create_task(auto_shutdown())

# --- 起動時通知 ---
@bot.event
async def on_ready():
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send("☀️ 起きた")
    print("✅ 起動完了")

# --- Botの起動実行 ---
bot.run(os.getenv("DISCORD_TOKEN"))