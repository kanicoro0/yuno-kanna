from typing import Optional

import discord
from discord import app_commands

from yuno.commands.admin_service import (
    ATTENTION_STATUSES, INTEREST_STATUSES, MEMORY_STATUSES, CoreAdminService,
)


def create_memory_group(admin: CoreAdminService) -> app_commands.Group:
    group = app_commands.Group(name="memory", description="この場のMemoryMarkを管理します")

    @group.command(name="list", description="MemoryMarkを表示します")
    async def memory_list(
        interaction: discord.Interaction, status: str = "active",
        limit: app_commands.Range[int, 1, 20] = 10,
    ) -> None:
        if status not in {*MEMORY_STATUSES, "all"}:
            await _reply(interaction, "statusは pending / active / hidden / all です")
            return
        items = await admin.list_memory(_channel(interaction), _guild(interaction), status, limit)
        await _reply(interaction, _memory_text(items))

    @group.command(name="pending", description="pendingのMemoryMarkを表示します")
    async def memory_pending(
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 20] = 10,
    ) -> None:
        items = await admin.list_memory(_channel(interaction), _guild(interaction), "pending", limit)
        await _reply(interaction, _memory_text(items))

    @group.command(name="activate", description="MemoryMarkをactiveにします")
    async def memory_activate(interaction: discord.Interaction, public_id: str) -> None:
        await _memory_status(interaction, admin, public_id, "active")

    @group.command(name="hide", description="MemoryMarkをhiddenにします")
    async def memory_hide(interaction: discord.Interaction, public_id: str) -> None:
        await _memory_status(interaction, admin, public_id, "hidden")

    @group.command(name="restore", description="MemoryMarkをpendingへ戻します")
    async def memory_restore(interaction: discord.Interaction, public_id: str) -> None:
        await _memory_status(interaction, admin, public_id, "pending")

    @group.command(name="add", description="この場へMemoryMarkを手動追加します")
    async def memory_add(
        interaction: discord.Interaction, content: str,
        status: str = "pending", kind: str = "pin",
    ) -> None:
        if status not in {"pending", "active"} or kind not in {"pin", "correction"}:
            await _reply(interaction, "statusまたはkindが不正です")
            return
        item = await admin.add_memory(
            _channel(interaction), _guild(interaction), content, status, kind
        )
        await _reply(interaction, f"{item.public_id} を {item.status} で追加しました")

    return group


def create_attention_group(admin: CoreAdminService) -> app_commands.Group:
    group = app_commands.Group(name="attention", description="この場のAttentionを管理します")

    @group.command(name="list", description="Attentionを表示します")
    async def attention_list(
        interaction: discord.Interaction, status: str = "open",
        limit: app_commands.Range[int, 1, 20] = 10,
    ) -> None:
        if status not in {*ATTENTION_STATUSES, "all"}:
            await _reply(interaction, "statusは open / closed / hidden / all です")
            return
        items = await admin.list_attention(_channel(interaction), _guild(interaction), status, limit)
        text = "\n".join(
            f"{item.public_id} [{item.status}] rank={item.rank:.2f} {_preview(item.text)}"
            for item in items
        ) or "この場には該当するAttentionがありません"
        await _reply(interaction, text)

    @group.command(name="close", description="Attentionをclosedにします")
    async def attention_close(interaction: discord.Interaction, public_id: str) -> None:
        await _attention_status(interaction, admin, public_id, "closed")

    @group.command(name="hide", description="Attentionをhiddenにします")
    async def attention_hide(interaction: discord.Interaction, public_id: str) -> None:
        await _attention_status(interaction, admin, public_id, "hidden")

    @group.command(name="reopen", description="Attentionをopenへ戻します")
    async def attention_reopen(interaction: discord.Interaction, public_id: str) -> None:
        await _attention_status(interaction, admin, public_id, "open")

    @group.command(name="add", description="この場へAttentionを手動追加します")
    async def attention_add(
        interaction: discord.Interaction, text: str,
        rank: app_commands.Range[float, 0.0, 1.0] = 0.5,
    ) -> None:
        item = await admin.add_attention(_channel(interaction), _guild(interaction), text, rank)
        await _reply(interaction, f"{item.public_id} をopenで追加しました")

    return group


def create_interest_group(admin: CoreAdminService) -> app_commands.Group:
    group = app_commands.Group(name="interest", description="この場の関心語を管理します")

    @group.command(name="list", description="関心語を表示します")
    async def interest_list(
        interaction: discord.Interaction, status: str = "active",
        limit: app_commands.Range[int, 1, 20] = 10,
    ) -> None:
        if status not in {*INTEREST_STATUSES, "all"}:
            await _reply(interaction, "statusは active / sleeping / hidden / all です")
            return
        items = await admin.list_interest(_channel(interaction), _guild(interaction), status, limit)
        text = "\n".join(
            f"{item.public_id} [{item.status}] weight={item.weight:.2f} {_preview(item.term)}"
            for item in items
        ) or "この場には該当する関心語がありません"
        await _reply(interaction, text)

    @group.command(name="add", description="この場へ関心語を手動追加します")
    async def interest_add(
        interaction: discord.Interaction, term: str,
        weight: app_commands.Range[float, 0.0, 1.0] = 0.3,
    ) -> None:
        item = await admin.add_interest(_channel(interaction), _guild(interaction), term, weight)
        await _reply(interaction, f"{item.public_id} をactiveで追加しました")

    @group.command(name="hide", description="関心語をhiddenにします")
    async def interest_hide(interaction: discord.Interaction, public_id: str) -> None:
        await _interest_status(interaction, admin, public_id, "hidden")

    @group.command(name="sleep", description="関心語をsleepingにします")
    async def interest_sleep(interaction: discord.Interaction, public_id: str) -> None:
        await _interest_status(interaction, admin, public_id, "sleeping")

    @group.command(name="wake", description="関心語をactiveへ戻します")
    async def interest_wake(interaction: discord.Interaction, public_id: str) -> None:
        await _interest_status(interaction, admin, public_id, "active")

    return group


async def _memory_status(interaction, admin, public_id, status):
    item = await admin.set_memory_status(_channel(interaction), public_id, status)
    await _reply(interaction, f"{public_id} を{status}にしました" if item else "この場では見つかりません")


async def _attention_status(interaction, admin, public_id, status):
    item = await admin.set_attention_status(_channel(interaction), public_id, status)
    await _reply(interaction, f"{public_id} を{status}にしました" if item else "この場では見つかりません")


async def _interest_status(interaction, admin, public_id, status):
    item = await admin.set_interest_status(_channel(interaction), public_id, status)
    await _reply(interaction, f"{public_id} を{status}にしました" if item else "この場では見つかりません")


def _memory_text(items) -> str:
    return "\n".join(
        f"{item.public_id} [{item.status}/{item.kind}] confidence={item.confidence:.2f} {_preview(item.content)}"
        for item in items
    ) or "この場には該当するMemoryMarkがありません"


def _preview(value: str) -> str:
    text = value.replace("\n", " ").strip()
    return text if len(text) <= 80 else text[:79] + "…"


def _channel(interaction: discord.Interaction) -> str:
    if interaction.channel_id is None:
        raise ValueError("channel is unavailable")
    return str(interaction.channel_id)


def _guild(interaction: discord.Interaction) -> Optional[str]:
    return str(interaction.guild_id) if interaction.guild_id is not None else None


async def _reply(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.send_message(text[:2000], ephemeral=True)
