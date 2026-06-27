from typing import Optional

import discord

from yuno.core.config import Settings
from yuno.infra.openai_client import OpenAIJsonClient
from yuno.memory.storage import MemoryStorage
from yuno.runtime.settings import RuntimeSettings


GUIDE_TEXT = """ゆの v2

`/memory user|server|channel`  記憶
`/memory get|search`  ID表示・検索
`/status`  状態
`/sleep` `/wake`  眠る・起きる
`/autorespond`  非メンション設定
`/settings memory_view`  表示モード

詳しい使い方はREADMEに置いてあるよ"""


def register_general_commands(
    tree: discord.app_commands.CommandTree,
    settings: Settings,
    storage: MemoryStorage,
    runtime_settings: RuntimeSettings,
    ai_client: OpenAIJsonClient,
) -> None:
    @tree.command(name="guide", description="主要commandを表示します")
    async def guide(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(GUIDE_TEXT, ephemeral=True)

    @tree.command(name="status", description="ゆの v2の状態を表示します")
    async def status(interaction: discord.Interaction, debug: bool = False) -> None:
        if debug and (settings.owner_id is None or interaction.user.id != settings.owner_id):
            await interaction.response.send_message("debug表示は、いまは開けないよ", ephemeral=True)
            return
        try:
            records = await storage.load()
            memory_state = "ok"
        except (OSError, ValueError):
            records = []
            memory_state = "error"
        sleeping = await runtime_settings.is_sleeping(interaction.guild_id, interaction.channel_id)
        auto_reply = await runtime_settings.auto_reply_allowed(
            interaction.guild_id, interaction.channel_id
        )
        lines = [
            "ゆの v2の状態",
            "",
            f"env: {settings.yuno_env}",
            f"OpenAI: {'mock' if ai_client.is_mock else 'configured'}",
            f"memory: {memory_state}",
            f"sleep: {'sleeping' if sleeping else 'awake'}",
            f"nonmention: {'on' if auto_reply else 'off'}",
            "rate limit: on",
        ]
        if debug:
            snapshot = await runtime_settings.snapshot()
            scopes = [f"user:{interaction.user.id}"]
            if interaction.guild_id:
                scopes += [f"guild:{interaction.guild_id}", f"channel:{interaction.channel_id}"]
            counts = {scope: len([record for record in records if record.state == "active" and record.scope == scope]) for scope in scopes}
            sync_mode = (
                f"guild:{settings.discord_guild_id}"
                if settings.yuno_env.casefold() == "dev" and settings.discord_guild_id
                else "global"
            )
            lines += [
                "",
                f"memory file: {settings.memory_file}",
                f"changelog: {settings.memory_changelog_file}",
                f"sync: {sync_mode}",
                f"scope counts: {counts}",
                f"sleep config: {snapshot['sleep']}",
                "rate: user 10s / channel 5s / global 20 per 60s",
            ]
        await interaction.response.send_message("\n".join(lines)[:2000], ephemeral=True)
