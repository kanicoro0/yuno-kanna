import discord
from discord import app_commands

from yuno.runtime.settings import RuntimeSettings


def _can_manage_channel(interaction: discord.Interaction) -> bool:
    return bool(interaction.guild_id and interaction.permissions.manage_channels)


def _can_manage_server(interaction: discord.Interaction) -> bool:
    return bool(interaction.guild_id and interaction.permissions.manage_guild)


def register_sleep_commands(
    tree: discord.app_commands.CommandTree,
    runtime_settings: RuntimeSettings,
) -> None:
    @tree.command(name="sleep", description="このチャンネルで、ゆのを眠らせます")
    @app_commands.guild_only()
    async def sleep(interaction: discord.Interaction) -> None:
        if not _can_manage_channel(interaction):
            await interaction.response.send_message("眠る場所を変える権限がないみたい", ephemeral=True)
            return
        await runtime_settings.set_sleep("channels", interaction.channel_id, True)
        await interaction.response.send_message("ゆの、ここでは少し眠るね", ephemeral=True)

    @tree.command(name="wake", description="このチャンネルで、ゆのを起こします")
    @app_commands.guild_only()
    async def wake(interaction: discord.Interaction) -> None:
        if not _can_manage_channel(interaction):
            await interaction.response.send_message("起こす場所を変える権限がないみたい", ephemeral=True)
            return
        await runtime_settings.set_sleep("channels", interaction.channel_id, False)
        await interaction.response.send_message("ゆの、目が覚めた", ephemeral=True)


def create_autorespond_group(runtime_settings: RuntimeSettings) -> app_commands.Group:
    group = app_commands.Group(name="autorespond", description="非メンション反応を設定します")

    @group.command(name="status", description="この場所の非メンション設定を表示します")
    @app_commands.guild_only()
    async def status(interaction: discord.Interaction) -> None:
        snapshot = await runtime_settings.snapshot()
        guild_value = snapshot["auto_reply"]["guilds"].get(str(interaction.guild_id))
        channel_value = snapshot["auto_reply"]["channels"].get(str(interaction.channel_id))
        effective = await runtime_settings.auto_reply_allowed(interaction.guild_id, interaction.channel_id)
        text = (
            "非メンション反応の設定\n\n"
            f"server: `{'未設定' if guild_value is None else ('on' if guild_value else 'off')}`\n"
            f"channel: `{'未設定' if channel_value is None else ('on' if channel_value else 'off')}`\n"
            f"この場所での結果: `{'on' if effective else 'off'}`\n\n"
            "serverがoffなら全体を止めるよ。それ以外ではchannel設定を先に見るよ"
        )
        await interaction.response.send_message(text, ephemeral=True)

    @group.command(name="server", description="サーバー全体の非メンション反応を切り替えます")
    @app_commands.guild_only()
    @app_commands.describe(enabled="有効にする場合はtrue")
    async def server(interaction: discord.Interaction, enabled: bool) -> None:
        if not _can_manage_server(interaction):
            await interaction.response.send_message("サーバー全体を変える権限がないみたい", ephemeral=True)
            return
        await runtime_settings.set_auto_reply("guilds", interaction.guild_id, enabled)
        state = "許可したよ" if enabled else "止めたよ"
        await interaction.response.send_message(f"このサーバーの非メンション反応を{state}", ephemeral=True)

    @group.command(name="channel", description="このチャンネルの非メンション反応を切り替えます")
    @app_commands.guild_only()
    @app_commands.describe(enabled="有効にする場合はtrue")
    async def channel(interaction: discord.Interaction, enabled: bool) -> None:
        if not _can_manage_channel(interaction):
            await interaction.response.send_message("この場所を変える権限がないみたい", ephemeral=True)
            return
        await runtime_settings.set_auto_reply("channels", interaction.channel_id, enabled)
        state = "許可したよ" if enabled else "止めたよ"
        await interaction.response.send_message(f"このチャンネルの非メンション反応を{state}", ephemeral=True)

    return group
