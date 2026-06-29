from typing import Optional

import discord
from discord import app_commands

from yuno.listening.service import ListeningChannelService


def create_listening_group(service: ListeningChannelService) -> app_commands.Group:
    group = app_commands.Group(name="listening", description="listening対象を管理します")

    @group.command(name="list", description="現在のlistening対象を表示します")
    async def listening_list(interaction: discord.Interaction) -> None:
        items = await service.list_all()
        text = "\n".join(
            f"<#{item.discord_channel_id}> source: {item.source}" for item in items
        ) or "listening対象はありません"
        await _reply(interaction, text)

    @group.command(name="add", description="listening対象を追加します")
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
            await _reply(interaction, "guildのテキストチャンネルで実行してください")
            return
        result = await service.add(str(target.id), str(interaction.guild_id))
        text = "追加しました" if result.changed else "すでにlistening対象です"
        await _reply(interaction, text)

    @group.command(name="remove", description="DB由来のlistening対象を解除します")
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
            await _reply(interaction, "guildのテキストチャンネルで実行してください")
            return
        result = await service.remove(str(target.id))
        if result.reason == "env_protected":
            text = ".env由来なのでcommandでは解除できません"
        elif result.changed:
            text = "解除しました"
        else:
            text = "DB由来のlistening対象ではありません"
        await _reply(interaction, text)

    @group.command(name="clear", description="このguildのDB由来設定を解除します")
    async def listening_clear(interaction: discord.Interaction) -> None:
        if not await _can_change(interaction):
            return
        if interaction.guild_id is None:
            await _reply(interaction, "guildで実行してください")
            return
        count = await service.clear(str(interaction.guild_id))
        await _reply(interaction, f"DB由来の設定を{count}件解除しました")

    return group


async def _can_change(interaction: discord.Interaction) -> bool:
    if interaction.guild_id is None:
        await _reply(interaction, "DMでは変更できません")
        return False
    permissions = getattr(interaction.user, "guild_permissions", None)
    if not permissions or not permissions.manage_channels:
        await _reply(interaction, "Manage Channels権限が必要です")
        return False
    return True


async def _reply(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.send_message(text[:2000], ephemeral=True)
