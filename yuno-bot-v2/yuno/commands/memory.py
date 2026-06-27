from dataclasses import replace
from typing import List, Optional

import discord
from discord import app_commands

from yuno.memory.records import MemoryRecord, new_memory_id, utc_now
from yuno.memory.storage import MemoryStorage
from yuno.text import (
    NO_MEMORIES, memory_added, memory_deleted, memory_edited, memory_not_found,
)


DEFAULT_ROUTES = ["semantic", "keyword", "tag"]
DEFAULT_CONTEXTS = ["dm", "mention", "prefix", "nonmention"]


def _split_values(value: Optional[str], default: List[str]) -> List[str]:
    if not value:
        return list(default)
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _scope(interaction: discord.Interaction, kind: str) -> Optional[str]:
    if kind == "user":
        return f"user:{interaction.user.id}"
    if kind == "server" and interaction.guild_id:
        return f"guild:{interaction.guild_id}"
    if kind == "channel" and interaction.guild_id and interaction.channel_id:
        return f"channel:{interaction.channel_id}"
    return None


def _can_mutate(interaction: discord.Interaction, kind: str) -> bool:
    if kind == "user":
        return True
    permissions = interaction.permissions
    if kind == "server":
        return permissions.manage_guild
    return permissions.manage_channels


def _format_records(records: List[MemoryRecord], scope: str) -> str:
    if not records:
        return f"scope: `{scope}`\n\n{NO_MEMORIES}"
    blocks = [f"scope: `{scope}`  /  {len(records)}件"]
    for record in records:
        tags = ", ".join(record.tags) or "タグなし"
        blocks.append(
            f"`{record.id}`  weight:{record.weight}\n"
            f"{record.content}\n"
            f"routes: {', '.join(record.routes)} / tags: {tags}"
        )
    text = "\n\n".join(blocks)
    return text if len(text) <= 1950 else text[:1900] + "\n\n…少し多いから、ここで表示を止めたよ"


def _create_scope_group(kind: str, storage: MemoryStorage) -> app_commands.Group:
    labels = {"user": "自分", "server": "サーバー", "channel": "チャンネル"}
    group = app_commands.Group(name=kind, description=f"{labels[kind]}scopeの記憶を扱います")

    @group.command(name="show", description=f"{labels[kind]}scopeの記憶を表示します")
    async def show(interaction: discord.Interaction) -> None:
        scope = _scope(interaction, kind)
        if scope is None:
            await interaction.response.send_message("この操作はサーバーの中で使ってね", ephemeral=True)
            return
        records = await storage.search_recent([scope], limit=20)
        await interaction.response.send_message(_format_records(records, scope), ephemeral=True)

    @group.command(name="add", description=f"{labels[kind]}scopeへ記憶を追加します")
    @app_commands.describe(
        content="覚える内容",
        tags="カンマ区切りのタグ（省略時 note）",
        routes="カンマ区切りのroute",
        contexts="カンマ区切りのcontext",
        weight="記憶の強さ（1〜5）",
    )
    async def add(
        interaction: discord.Interaction,
        content: str,
        tags: Optional[str] = None,
        routes: Optional[str] = None,
        contexts: Optional[str] = None,
        weight: app_commands.Range[int, 1, 5] = 3,
    ) -> None:
        scope = _scope(interaction, kind)
        if scope is None:
            await interaction.response.send_message("この操作はサーバーの中で使ってね", ephemeral=True)
            return
        if not _can_mutate(interaction, kind):
            await interaction.response.send_message("ここを書き換える権限がないみたい", ephemeral=True)
            return
        now = utc_now()
        record = MemoryRecord(
            id=new_memory_id(),
            scope=scope,
            content=content.strip(),
            routes=_split_values(routes, DEFAULT_ROUTES),
            contexts=_split_values(contexts, DEFAULT_CONTEXTS),
            weight=int(weight),
            tags=_split_values(tags, ["note"]),
            created_at=now,
            updated_at=now,
        )
        try:
            saved = await storage.upsert(record)
        except ValueError as error:
            await interaction.response.send_message(f"その形では覚えられなかったよ: {error}", ephemeral=True)
            return
        await interaction.response.send_message(memory_added(saved.id, scope), ephemeral=True)

    @group.command(name="edit", description=f"{labels[kind]}scopeの記憶本文を書き換えます")
    @app_commands.describe(memory_id="mem_から始まるID", content="新しい記憶本文")
    async def edit(interaction: discord.Interaction, memory_id: str, content: str) -> None:
        scope = _scope(interaction, kind)
        if scope is None:
            await interaction.response.send_message("この操作はサーバーの中で使ってね", ephemeral=True)
            return
        if not _can_mutate(interaction, kind):
            await interaction.response.send_message("ここを書き換える権限がないみたい", ephemeral=True)
            return
        record = await storage.get_by_id(memory_id.strip())
        if record is None or record.state != "active" or record.scope != scope:
            await interaction.response.send_message(memory_not_found(memory_id), ephemeral=True)
            return
        try:
            await storage.upsert(replace(record, content=content.strip()))
        except ValueError as error:
            await interaction.response.send_message(f"その形には書き換えられなかったよ: {error}", ephemeral=True)
            return
        await interaction.response.send_message(memory_edited(record.id, scope), ephemeral=True)

    @group.command(name="delete", description=f"{labels[kind]}scopeの記憶を外します")
    @app_commands.describe(memory_id="mem_から始まるID")
    async def delete(interaction: discord.Interaction, memory_id: str) -> None:
        scope = _scope(interaction, kind)
        if scope is None:
            await interaction.response.send_message("この操作はサーバーの中で使ってね", ephemeral=True)
            return
        if not _can_mutate(interaction, kind):
            await interaction.response.send_message("ここを書き換える権限がないみたい", ephemeral=True)
            return
        record = await storage.get_by_id(memory_id.strip())
        if record is None or record.state != "active" or record.scope != scope:
            await interaction.response.send_message(memory_not_found(memory_id), ephemeral=True)
            return
        await storage.mark_deleted(record.id)
        await interaction.response.send_message(memory_deleted(record.id, scope), ephemeral=True)

    return group


def create_memory_group(storage: MemoryStorage) -> app_commands.Group:
    root = app_commands.Group(name="memory", description="scopeごとに記憶を扱います")
    for kind in ("user", "server", "channel"):
        root.add_command(_create_scope_group(kind, storage))
    return root
