from typing import List

import discord
from discord import app_commands

from yuno.core.config import Settings
from yuno.core.preplanning import RateLimiter
from yuno.infra.openai_client import OpenAIJsonClient
from yuno.memory.storage import MemoryStorage
from yuno.runtime.settings import RuntimeSettings


GUIDE_TEXT = """ゆの v2で、いま使えるもの

`/memory user show|add|edit|delete` — きみの記憶
`/memory server show|add|edit|delete` — このサーバーの記憶
`/memory channel show|add|edit|delete` — このチャンネルの記憶
`/status` — いまの動作状態
`/sleep` / `/wake` — このチャンネルで眠る / 起きる
`/autorespond status` — 非メンション反応の設定を見る
`/autorespond server` / `/autorespond channel` — 設定を切り替える

reminderは、まだ準備中だよ"""


def _current_scopes(interaction: discord.Interaction) -> List[str]:
    scopes = [f"user:{interaction.user.id}"]
    if interaction.guild_id:
        scopes.extend((f"guild:{interaction.guild_id}", f"channel:{interaction.channel_id}"))
    return scopes


def register_general_commands(
    tree: discord.app_commands.CommandTree,
    settings: Settings,
    storage: MemoryStorage,
    runtime_settings: RuntimeSettings,
    ai_client: OpenAIJsonClient,
) -> None:
    @tree.command(name="guide", description="ゆの v2で使える機能を表示します")
    async def guide(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(GUIDE_TEXT, ephemeral=True)

    @tree.command(name="status", description="ゆの v2の現在状態を表示します")
    async def status(interaction: discord.Interaction) -> None:
        scopes = _current_scopes(interaction)
        counts = {scope: len(await storage.list_active([scope])) for scope in scopes}
        guild_id = interaction.guild_id
        channel_id = interaction.channel_id
        sleeping = await runtime_settings.is_sleeping(guild_id, channel_id)
        auto_reply = await runtime_settings.auto_reply_allowed(guild_id, channel_id)
        sync_mode = (
            f"guild:{settings.discord_guild_id}"
            if settings.yuno_env.casefold() == "dev" and settings.discord_guild_id
            else "global"
        )
        user_scope = f"user:{interaction.user.id}"
        guild_scope = f"guild:{guild_id}" if guild_id else None
        channel_scope = f"channel:{channel_id}" if guild_id and channel_id else None
        lines = [
            "ゆの v2の現在地",
            "",
            f"環境: `{settings.yuno_env}`",
            f"memory: `{settings.memory_file}`",
            f"OpenAI: `{'mock fallback' if ai_client.is_mock else 'configured'}`",
            f"slash sync: `{sync_mode}`",
            f"sleep: `{'sleeping' if sleeping else 'awake'}`",
            f"非メンション反応: `{'on' if auto_reply else 'off'}`",
            f"user記憶: `{counts[user_scope]}`",
            f"server記憶: `{counts.get(guild_scope, 0) if guild_scope else '-'}`",
            f"channel記憶: `{counts.get(channel_scope, 0) if channel_scope else '-'}`",
            (
                "rate limit: `user 10秒 / channel 5秒 / "
                f"global {RateLimiter.GLOBAL_MAX_REQUESTS}回/{int(RateLimiter.GLOBAL_WINDOW_SECONDS)}秒`"
            ),
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)
