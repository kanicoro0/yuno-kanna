from typing import List, Optional

import discord
from discord import app_commands

from yuno.memory.records import MemoryRecord
from yuno.memory.storage import MemoryStorage


def _scopes(interaction: discord.Interaction) -> List[str]:
    result = [f"user:{interaction.user.id}"]
    if interaction.guild_id:
        result.append(f"guild:{interaction.guild_id}")
        result.append(f"channel:{interaction.channel_id}")
    return result


def _format_records(records: List[MemoryRecord], title: str) -> str:
    if not records:
        return f"{title}\n\n該当する記憶はありません。"
    blocks = [title]
    for record in records:
        tags = ", ".join(record.tags) or "タグなし"
        blocks.append(
            f"`{record.id}`  weight:{record.weight}\n"
            f"{record.content}\n"
            f"scope: `{record.scope}` / tags: {tags}"
        )
    text = "\n\n".join(blocks)
    return text if len(text) <= 1950 else text[:1900] + "\n\n…表示を省略しました。検索を絞ってください。"


async def _find(storage: MemoryStorage, scopes: List[str], query: Optional[str]) -> List[MemoryRecord]:
    value = (query or "recent").strip()
    if value == "recent":
        return await storage.search_recent(scopes)
    if value.startswith("tag:"):
        return await storage.search_by_tag(scopes, value[4:])
    if value.startswith("search:"):
        return await storage.search_by_text(scopes, value[7:])
    return []


def create_memory_group(storage: MemoryStorage) -> app_commands.Group:
    group = app_commands.Group(name="memory", description="記憶を探したり編集したりします")

    @group.command(name="show", description="記憶を最近・タグ・本文から探します")
    @app_commands.describe(query="recent / tag:tone / search:話し方（省略時はrecent）")
    async def show(interaction: discord.Interaction, query: Optional[str] = None) -> None:
        await interaction.response.defer(ephemeral=True)
        records = await _find(storage, _scopes(interaction), query)
        await interaction.followup.send(_format_records(records, "記憶"), ephemeral=True)

    @group.command(name="edit", description="編集対象の記憶を探します（編集UIは初期実装）")
    @app_commands.describe(query="recent / tag:tone / search:話し方 / id:mem_xxx")
    async def edit(interaction: discord.Interaction, query: Optional[str] = None) -> None:
        await interaction.response.defer(ephemeral=True)
        scopes = _scopes(interaction)
        if not query:
            text = (
                "記憶を編集します\n\n"
                "1. 最近の記憶を見る\n2. タグで探す\n3. 本文で探す\n\n"
                "または:\n- `/memory edit query:recent`\n- `/memory edit query:tag:tone`\n"
                "- `/memory edit query:search:話し方`\n\n"
                "本格的な編集フォームはTODOです。"
            )
        elif query.strip().startswith("id:"):
            memory_id = query.strip()[3:]
            record = await storage.get_by_id(memory_id)
            if record is None or record.scope not in scopes:
                text = "その記憶は見つからないか、この場所から編集できません。"
            else:
                text = _format_records([record], "編集対象（詳細表示）") + (
                    "\n\nTODO: content / tags / routes / contexts / weight / state の編集フォームを追加する。"
                )
        else:
            records = await _find(storage, scopes, query)
            text = _format_records(records, "編集対象を選ぶための検索結果")
            text += "\n\n編集候補のIDを `/memory edit query:id:mem_xxx` に渡してください。"
        await interaction.followup.send(text[:2000], ephemeral=True)

    return group
