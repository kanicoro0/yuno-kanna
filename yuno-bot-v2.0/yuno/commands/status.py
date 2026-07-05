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
        "いまの聞こえ方\n"
        "- DM: 残して返す\n"
        "- mention: 残してreplyで返す\n"
        "- ゆのへのreply: 残してreplyで返す\n"
        f"- 聞き耳: {channels}\n"
        "  ふつうの発言は残す。返すのは、拾う理由がある時だけ\n"
        "- 聞き耳でゆのへ向いた発言: 残して返す\n"
        "- それ以外: 残さない\n"
        f"- 呼び名: {names}"
    )


def create_status_command(
    listening: ListeningChannelService, call_names: Tuple[str, ...]
) -> app_commands.Command:
    @app_commands.command(name="status", description="いまの聞き方を見る")
    async def status(interaction: discord.Interaction) -> None:
        listening_items = await listening.list_all()
        await interaction.response.send_message(
            status_text(listening_items, call_names),
            ephemeral=True,
        )

    return status
