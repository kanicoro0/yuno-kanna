from typing import Optional

import discord
from discord import app_commands

from yuno.runtime.settings import RuntimeSettings


SLEEP_SCOPES = [
    app_commands.Choice(name="channel", value="channel"),
    app_commands.Choice(name="server", value="server"),
    app_commands.Choice(name="global", value="global"),
]


def _can_manage_channel(interaction: discord.Interaction) -> bool:
    return bool(interaction.guild_id and interaction.permissions.manage_channels)


def _can_manage_server(interaction: discord.Interaction) -> bool:
    return bool(interaction.guild_id and interaction.permissions.manage_guild)


async def _set_sleep(
    interaction: discord.Interaction,
    runtime_settings: RuntimeSettings,
    owner_id: Optional[int],
    scope: str,
    enabled: bool,
) -> Optional[str]:
    if scope == "channel":
        if not _can_manage_channel(interaction):
            return "このチャンネルを変える権限がないみたい"
        await runtime_settings.set_sleep("channels", interaction.channel_id, enabled)
    elif scope == "server":
        if not _can_manage_server(interaction):
            return "このサーバーを変える権限がないみたい"
        await runtime_settings.set_sleep("guilds", interaction.guild_id, enabled)
    elif scope == "global":
        if owner_id is None or interaction.user.id != owner_id:
            return "globalは、いまは触れないよ"
        await runtime_settings.set_sleep("global", None, enabled)
    else:
        return "そのscopeは選べないよ"
    return None


def register_sleep_commands(
    tree: discord.app_commands.CommandTree,
    runtime_settings: RuntimeSettings,
    owner_id: Optional[int],
) -> None:
    @tree.command(name="sleep", description="scopeを指定して、ゆのを眠らせます")
    @app_commands.choices(scope=SLEEP_SCOPES)
    async def sleep(
        interaction: discord.Interaction,
        scope: str = "channel",
    ) -> None:
        error = await _set_sleep(interaction, runtime_settings, owner_id, scope, True)
        await interaction.response.send_message(error or f"{scope}で眠るね", ephemeral=True)

    @tree.command(name="wake", description="scopeを指定して、ゆのを起こします")
    @app_commands.choices(scope=SLEEP_SCOPES)
    async def wake(
        interaction: discord.Interaction,
        scope: str = "channel",
    ) -> None:
        error = await _set_sleep(interaction, runtime_settings, owner_id, scope, False)
        await interaction.response.send_message(error or f"{scope}で目が覚めた", ephemeral=True)


def create_autorespond_group(runtime_settings: RuntimeSettings) -> app_commands.Group:
    group = app_commands.Group(name="autorespond", description="非メンション反応の設定")

    @group.command(name="status", description="この場所の設定を表示します")
    @app_commands.guild_only()
    async def status(interaction: discord.Interaction) -> None:
        snapshot = await runtime_settings.snapshot()
        guild_value = snapshot["auto_reply"]["guilds"].get(str(interaction.guild_id))
        channel_value = snapshot["auto_reply"]["channels"].get(str(interaction.channel_id))
        effective = await runtime_settings.auto_reply_allowed(interaction.guild_id, interaction.channel_id)
        text = (
            "非メンション反応\n"
            f"server: {'unset' if guild_value is None else ('on' if guild_value else 'off')}\n"
            f"channel: {'unset' if channel_value is None else ('on' if channel_value else 'off')}\n"
            f"effective: {'on' if effective else 'off'}"
        )
        await interaction.response.send_message(text, ephemeral=True)

    @group.command(name="server", description="サーバー全体の設定を切り替えます")
    async def server(interaction: discord.Interaction, enabled: bool) -> None:
        if not _can_manage_server(interaction):
            await interaction.response.send_message("サーバーを変える権限がないみたい", ephemeral=True)
            return
        await runtime_settings.set_auto_reply("guilds", interaction.guild_id, enabled)
        await interaction.response.send_message(f"server: {'on' if enabled else 'off'}", ephemeral=True)

    @group.command(name="channel", description="このチャンネルの設定を切り替えます")
    async def channel(interaction: discord.Interaction, enabled: bool) -> None:
        if not _can_manage_channel(interaction):
            await interaction.response.send_message("チャンネルを変える権限がないみたい", ephemeral=True)
            return
        await runtime_settings.set_auto_reply("channels", interaction.channel_id, enabled)
        await interaction.response.send_message(f"channel: {'on' if enabled else 'off'}", ephemeral=True)

    return group


def create_settings_group(
    runtime_settings: RuntimeSettings, owner_id: Optional[int]
) -> app_commands.Group:
    group = app_commands.Group(name="settings", description="ゆの v2の表示設定")

    @group.command(name="memory_view", description="記憶の表示モードを変更します")
    @app_commands.choices(mode=[
        app_commands.Choice(name="normal", value="normal"),
        app_commands.Choice(name="debug", value="debug"),
    ])
    async def memory_view(
        interaction: discord.Interaction, mode: app_commands.Choice[str]
    ) -> None:
        if mode.value == "debug" and (owner_id is None or interaction.user.id != owner_id):
            await interaction.response.send_message("debug表示は、いまは開けないよ", ephemeral=True)
            return
        await runtime_settings.set_memory_view(interaction.user.id, mode.value)
        await interaction.response.send_message(f"memory view: {mode.value}", ephemeral=True)

    return group
