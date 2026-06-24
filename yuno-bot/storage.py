import asyncio
import json
import os
import subprocess

from config import (
    BASE_DIR,
    CHAT_HISTORY_FILE,
    ENABLE_GIT_SAVE,
    GUILD_NOTES_FILE,
    LONGTERM_MEMORY_FILE,
    REMINDERS_FILE,
)


file_lock = asyncio.Lock()


def load_json_file(path: str):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}


async def write_json_async(path: str, data: dict):
    async with file_lock:
        def _write():
            with open(path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)

        return await asyncio.to_thread(_write)


async def save_to_git_async(commit_msg: str, error_reporter=None):
    if not ENABLE_GIT_SAVE:
        return

    def _run():
        files_to_commit = [
            path
            for path in (
                CHAT_HISTORY_FILE,
                GUILD_NOTES_FILE,
                LONGTERM_MEMORY_FILE,
                REMINDERS_FILE,
            )
            if os.path.isfile(path)
        ]
        if not files_to_commit:
            print("🔄 Git: 保存対象ファイルなし。コミット・プッシュはスキップ")
            return

        relative_files = [os.path.relpath(path, BASE_DIR) for path in files_to_commit]
        result = subprocess.run(
            ["git", "-C", BASE_DIR, "status", "--porcelain", "--"] + relative_files,
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout.strip():
            subprocess.run(
                ["git", "-C", BASE_DIR, "add", "--"] + relative_files,
                check=True,
            )
            subprocess.run(
                ["git", "-C", BASE_DIR, "commit", "-m", commit_msg, "--"] + relative_files,
                check=True,
            )
            subprocess.run(["git", "-C", BASE_DIR, "push"], check=True)
        else:
            print("🔄 Git: 変更なし。コミット・プッシュはスキップ")

    try:
        await asyncio.to_thread(_run)
    except subprocess.CalledProcessError as error:
        message = f"gitの保存に失敗したよ: {error}"
        if error_reporter:
            error_reporter(message)
        else:
            print(f"⚠️ {message}")
