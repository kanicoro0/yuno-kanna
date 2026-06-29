from typing import Optional

import discord
from discord import app_commands

from yuno.listening.service import ListeningChannelService


def create_listening_group(service: ListeningChannelService) -> app_commands.Group:
    group = app_commands.Group(name="listening", description="ゆのが聞き耳を立てる場所を管理します")

    @group.command(name="list", description="今ゆのが聞いている場所を表示します")
    async def listening_list(interaction: discord.Interaction) -> None:
        items = await service.list_all()
        text = "\n".join(
            f"<#{item.discord_channel_id}> 由来: {item.source}" for item in items
        ) or "ゆのが聞き耳を立てている場所は、まだないみたい"
        await _reply(interaction, text)

    @group.command(name="add", description="聞き耳の場所を追加します")
    async def listening_add(
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if not await _can_change(interaction):
            return
        target = channel or interaction.channel
        if (
            interaction.guild_id is None
            or not isinstance(target, discord.TextChannel)
            or target.guild.id != interaction.guild_id
        ):
            await _reply(interaction, "サーバーのテキストチャンネルで実行してね")
            return
        result = await service.add(str(target.id), str(interaction.guild_id))
        text = "聞き耳の場所に追加したよ" if result.changed else "そこはもう聞き耳の場所だよ"
        await _reply(interaction, text)

    @group.command(name="remove", description="後から追加した聞き耳の場所を解除します")
    async def listening_remove(
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if not await _can_change(interaction):
            return
        target = channel or interaction.channel
        if (
            interaction.guild_id is None
            or not isinstance(target, discord.TextChannel)
            or target.guild.id != interaction.guild_id
        ):
            await _reply(interaction, "サーバーのテキストチャンネルで実行してね")
            return
        result = await service.remove(str(target.id))
        if result.reason == "env_protected":
            text = ".envで決めた場所なので、コマンドでは解除できないよ"
        elif result.changed:
            text = "聞き耳を少し閉じたよ"
        else:
            text = "そこはDB由来の聞き耳ではないみたい"
        await _reply(interaction, text)

    @group.command(name="clear", description="このサーバーで後から追加した聞き耳設定を解除します")
    async def listening_clear(interaction: discord.Interaction) -> None:
        if not await _can_change(interaction):
            return
        if interaction.guild_id is None:
            await _reply(interaction, "サーバーで実行してね")
            return
        count = await service.clear(str(interaction.guild_id))
        await _reply(interaction, f"DB由来の設定を{count}件解除したよ")

    return group


async def _can_change(interaction: discord.Interaction) -> bool:
    if interaction.guild_id is None:
        await _reply(interaction, "DMでは変更できないよ")
        return False
    permissions = getattr(interaction.user, "guild_permissions", None)
    if not permissions or not permissions.manage_channels:
        await _reply(interaction, "この耳を動かすには、チャンネル管理権限が必要です")
        return False
    return True


async def _reply(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.send_message(text[:2000], ephemeral=True)