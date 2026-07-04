from typing import Iterable, Tuple

import discord
from discord import app_commands

from yuno.listening.models import ListeningChannel
from yuno.listening.service import ListeningChannelService


def status_text(
    listening_items: Iterable[ListeningChannel], call_names: Iterable[str]
) -> str:
    channels = "、".join(
        f"<#{item.discord_channel_id}>({item.source})" for item in listening_items
    ) or "なし"
    names = "、".join(call_names)
    return (
        "ゆのが聞いている範囲\n"
        "- DM: 保存して返します\n"
        "- mention: 保存してreplyで返します\n"
        "- ゆのへのreply: 保存してreplyで返します\n"
        f"- 聞き耳の場所: {channels}\n"
        "  通常発言は保存します。関心語や開いた気がかりに触れた時だけCareReaderが読み、必要な時だけ返答します\n"
        "- 聞き耳の場所でゆのへ向けられた発言: 保存して返します\n"
        "- それ以外の通常発言: 保存しません\n"
        f"- 今の呼び名: {names}"
    )


def create_status_command(
    listening: ListeningChannelService, call_names: Tuple[str, ...]
) -> app_commands.Command:
    @app_commands.command(name="status", description="ゆのがどこで聞いて、どこで返すかを確認します")
    async def status(interaction: discord.Interaction) -> None:
        listening_items = await listening.list_all()
        await interaction.response.send_message(
            status_text(listening_items, call_names),
            ephemeral=True,
        )

    return status
