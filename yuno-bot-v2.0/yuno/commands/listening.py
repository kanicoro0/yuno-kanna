from typing import Optional

import discord
from discord import app_commands

from yuno.listening.service import ListeningChannelService


def create_listening_group(service: ListeningChannelService) -> app_commands.Group:
    group = app_commands.Group(name="listening", description="ゆのが聞く場所を管理")

    @group.command(name="list", description="いま聞いている場所を表示")
    async def listening_list(interaction: discord.Interaction) -> None:
        items = await service.list_all()
        text = "\n".join(
            f"<#{item.discord_channel_id}> 由来: {item.source}" for item in items
        ) or "聞いている場所はまだない"
        await _reply(interaction, text)

    @group.command(name="add", description="聞く場所を追加")
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
            await _reply(interaction, "サーバーのテキストチャンネルで使って")
            return
        result = await service.add(str(target.id), str(interaction.guild_id))
        text = "追加した" if result.changed else "すでに聞いている"
        await _reply(interaction, text)

    @group.command(name="remove", description="後から追加した場所を解除")
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
            await _reply(interaction, "サーバーのテキストチャンネルで使って")
            return
        result = await service.remove(str(target.id))
        if result.reason == "env_protected":
            text = ".env由来なのでコマンドでは解除できない"
        elif result.changed:
            text = "解除した"
        else:
            text = "DB由来の聞き場所ではない"
        await _reply(interaction, text)

    @group.command(name="clear", description="このサーバーで後から追加した設定を解除")
    async def listening_clear(interaction: discord.Interaction) -> None:
        if not await _can_change(interaction):
            return
        if interaction.guild_id is None:
            await _reply(interaction, "サーバーで使って")
            return
        count = await service.clear(str(interaction.guild_id))
        await _reply(interaction, f"DB由来の設定を{count}件解除")

    return group


async def _can_change(interaction: discord.Interaction) -> bool:
    if interaction.guild_id is None:
        await _reply(interaction, "DMでは変更できない")
        return False
    permissions = getattr(interaction.user, "guild_permissions", None)
    if not permissions or not permissions.manage_channels:
        await _reply(interaction, "チャンネル管理権限が必要")
        return False
    return True


async def _reply(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.send_message(text[:2000], ephemeral=True)
