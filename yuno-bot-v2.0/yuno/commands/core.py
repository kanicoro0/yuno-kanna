from typing import Optional

import discord
from discord import app_commands

from yuno.commands.admin_service import (
    ATTENTION_STATUSES, INTEREST_STATUSES, MEMORY_STATUSES, CoreAdminService,
)


def create_memory_group(admin: CoreAdminService) -> app_commands.Group:
    group = app_commands.Group(name="memory", description="この場の記憶の印を見たり、動かしたりします")

    @group.command(name="list", description="記憶の印を表示します")
    async def memory_list(
        interaction: discord.Interaction, status: str = "active",
        limit: app_commands.Range[int, 1, 20] = 10,
    ) -> None:
        if status not in {*MEMORY_STATUSES, "all"}:
            await _reply(interaction, "statusは pending / active / hidden / all から選んでね")
            return
        items = await admin.list_memory(_channel(interaction), _guild(interaction), status, limit)
        await _reply(interaction, _memory_text(items))

    @group.command(name="pending", description="まだ使う前の記憶の印を表示します")
    async def memory_pending(
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 20] = 10,
    ) -> None:
        items = await admin.list_memory(_channel(interaction), _guild(interaction), "pending", limit)
        await _reply(interaction, _memory_text(items))

    @group.command(name="activate", description="記憶の印を使えるようにします")
    async def memory_activate(interaction: discord.Interaction, public_id: str) -> None:
        await _memory_status(interaction, admin, public_id, "active")

    @group.command(name="hide", description="記憶の印を隠します")
    async def memory_hide(interaction: discord.Interaction, public_id: str) -> None:
        await _memory_status(interaction, admin, public_id, "hidden")

    @group.command(name="restore", description="記憶の印をpendingへ戻します")
    async def memory_restore(interaction: discord.Interaction, public_id: str) -> None:
        await _memory_status(interaction, admin, public_id, "pending")

    @group.command(name="add", description="この場へ記憶の印を手動で追加します")
    async def memory_add(
        interaction: discord.Interaction, content: str,
        status: str = "pending", kind: str = "pin",
    ) -> None:
        if status not in {"pending", "active"} or kind not in {"pin", "correction"}:
            await _reply(interaction, "statusかkindが少し違うみたい")
            return
        item = await admin.add_memory(
            _channel(interaction), _guild(interaction), content, status, kind
        )
        await _reply(interaction, f"{item.public_id} を {item.status} で追加したよ")

    return group


def create_attention_group(admin: CoreAdminService) -> app_commands.Group:
    group = app_commands.Group(name="attention", description="この場で気にしていることを見たり、閉じたりします")

    @group.command(name="list", description="気にしていることを表示します")
    async def attention_list(
        interaction: discord.Interaction, status: str = "open",
        limit: app_commands.Range[int, 1, 20] = 10,
    ) -> None:
        if status not in {*ATTENTION_STATUSES, "all"}:
            await _reply(interaction, "statusは open / closed / hidden / all から選んでね")
            return
        items = await admin.list_attention(_channel(interaction), _guild(interaction), status, limit)
        text = "\n".join(
            f"{item.public_id} [{item.status}] rank={item.rank:.2f} {_preview(item.text)}"
            for item in items
        ) or "この場には、該当する気にしていることはないみたい"
        await _reply(interaction, text)

    @group.command(name="close", description="気にしていることを閉じます")
    async def attention_close(interaction: discord.Interaction, public_id: str) -> None:
        await _attention_status(interaction, admin, public_id, "closed")

    @group.command(name="hide", description="気にしていることを隠します")
    async def attention_hide(interaction: discord.Interaction, public_id: str) -> None:
        await _attention_status(interaction, admin, public_id, "hidden")

    @group.command(name="reopen", description="気にしていることをもう一度openにします")
    async def attention_reopen(interaction: discord.Interaction, public_id: str) -> None:
        await _attention_status(interaction, admin, public_id, "open")

    @group.command(name="add", description="この場へ気にしていることを手動で追加します")
    async def attention_add(
        interaction: discord.Interaction, text: str,
        rank: app_commands.Range[float, 0.0, 1.0] = 0.5,
    ) -> None:
        item = await admin.add_attention(_channel(interaction), _guild(interaction), text, rank)
        await _reply(interaction, f"{item.public_id} をopenで追加したよ")

    return group


def create_interest_group(admin: CoreAdminService) -> app_commands.Group:
    group = app_commands.Group(name="interest", description="この場の関心語を見たり、眠らせたりします")

    @group.command(name="list", description="関心語を表示します")
    async def interest_list(
        interaction: discord.Interaction, status: str = "active",
        limit: app_commands.Range[int, 1, 20] = 10,
    ) -> None:
        if status not in {*INTEREST_STATUSES, "all"}:
            await _reply(interaction, "statusは active / sleeping / hidden / all から選んでね")
            return
        items = await admin.list_interest(_channel(interaction), _guild(interaction), status, limit)
        text = "\n".join(
            f"{item.public_id} [{item.status}] weight={item.weight:.2f} {_preview(item.term)}"
            for item in items
        ) or "この場には、該当する関心語はないみたい"
        await _reply(interaction, text)

    @group.command(name="add", description="この場へ関心語を手動で追加します")
    async def interest_add(
        interaction: discord.Interaction, term: str,
        weight: app_commands.Range[float, 0.0, 1.0] = 0.3,
    ) -> None:
        item = await admin.add_interest(_channel(interaction), _guild(interaction), term, weight)
        await _reply(interaction, f"{item.public_id} をactiveで追加したよ")

    @group.command(name="hide", description="関心語を隠します")
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
    await _reply(interaction, f"{public_id} を{status}にしたよ" if item else "この場では見つからないみたい")


async def _attention_status(interaction, admin, public_id, status):
    item = await admin.set_attention_status(_channel(interaction), public_id, status)
    await _reply(interaction, f"{public_id} を{status}にしたよ" if item else "この場では見つからないみたい")


async def _interest_status(interaction, admin, public_id, status):
    item = await admin.set_interest_status(_channel(interaction), public_id, status)
    await _reply(interaction, f"{public_id} を{status}にしたよ" if item else "この場では見つからないみたい")


def _memory_text(items) -> str:
    return "\n".join(
        f"{item.public_id} [{item.status}/{item.kind}] confidence={item.confidence:.2f} {_preview(item.content)}"
        for item in items
    ) or "この場には、該当する記憶の印はないみたい"


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