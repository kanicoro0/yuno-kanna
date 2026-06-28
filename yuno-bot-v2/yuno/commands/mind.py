from typing import Optional

import discord
from discord import app_commands

from yuno.mind.storage import MindStateStorage


MIND_SCOPES = [
    app_commands.Choice(name="この人", value="user"),
    app_commands.Choice(name="このサーバー", value="server"),
    app_commands.Choice(name="このチャンネル", value="channel"),
    app_commands.Choice(name="DM", value="dm"),
]
TARGET_LABELS = {"user": "この人", "server": "このサーバー", "channel": "このチャンネル", "dm": "DM"}


def _scope(interaction: discord.Interaction, kind: str) -> Optional[str]:
    if kind == "user":
        return f"user:{interaction.user.id}"
    if kind == "dm" and interaction.guild_id is None:
        return f"dm:{interaction.user.id}"
    if kind == "server" and interaction.guild_id:
        return f"guild:{interaction.guild_id}"
    if kind == "channel" and interaction.guild_id and interaction.channel_id:
        return f"channel:{interaction.channel_id}"
    return None


def _allowed(interaction: discord.Interaction, kind: str, owner_id: Optional[int]) -> bool:
    if kind in {"user", "dm"}:
        return True
    if owner_id is not None and interaction.user.id == owner_id:
        return True
    if kind == "server":
        return interaction.permissions.manage_guild
    return interaction.permissions.manage_channels


def create_mind_group(storage: MindStateStorage, owner_id: Optional[int]) -> app_commands.Group:
    group = app_commands.Group(name="mind", description="ゆのの今の頭の中")

    @group.command(name="show", description="ゆのの今の頭の中を表示します")
    @app_commands.choices(target=MIND_SCOPES)
    async def show(
        interaction: discord.Interaction,
        target: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        kind = target.value if target else ("dm" if interaction.guild_id is None else "channel")
        target_scope = _scope(interaction, kind)
        if target_scope is None or not _allowed(interaction, kind, owner_id):
            await interaction.response.send_message("そのmindは、ここから開けないよ", ephemeral=True)
            return
        state = await storage.get(target_scope)
        if state is None:
            await interaction.response.send_message(f"{TARGET_LABELS[kind]}\nまだ空だよ", ephemeral=True)
            return
        text = (
            f"{TARGET_LABELS[kind]}\n{state.summary or '-'}\n"
            f"開いている問い: {len(state.open_questions)} / 開いているnote: {len(state.active_note_ids)}\n"
            f"updated: {state.updated_at}"
        )
        await interaction.response.send_message(text[:2000], ephemeral=True)

    @group.command(name="clear", description="ゆのの今の頭の中を空にします")
    @app_commands.choices(target=MIND_SCOPES)
    async def clear(
        interaction: discord.Interaction,
        target: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        kind = target.value if target else ("dm" if interaction.guild_id is None else "channel")
        target_scope = _scope(interaction, kind)
        if target_scope is None or not _allowed(interaction, kind, owner_id):
            await interaction.response.send_message("そのmindは、ここから変えられないよ", ephemeral=True)
            return
        removed = await storage.clear(target_scope)
        await interaction.response.send_message("mindを空にしたよ" if removed else "もともと空だよ", ephemeral=True)

    @group.command(name="status", description="今の頭の中がある場所を表示します")
    async def status(interaction: discord.Interaction) -> None:
        scopes = ([f"dm:{interaction.user.id}", f"user:{interaction.user.id}"]
                  if interaction.guild_id is None else
                  [f"user:{interaction.user.id}", f"guild:{interaction.guild_id}",
                   f"channel:{interaction.channel_id}"])
        states = await storage.get_many(scopes)
        labels = (["DM", "この人"] if interaction.guild_id is None
                  else ["この人", "このサーバー", "このチャンネル"])
        lines = ["ゆのの今の頭の中", *[
            f"{label}: {'あり' if any(s.scope == scope for s in states) else '空'}"
            for label, scope in zip(labels, scopes)
        ]]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    return group
