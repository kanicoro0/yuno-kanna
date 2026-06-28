from typing import Optional

import discord
from discord import app_commands

from yuno.mind.storage import MindStateStorage


MIND_SCOPES = [
    app_commands.Choice(name="user", value="user"),
    app_commands.Choice(name="server", value="server"),
    app_commands.Choice(name="channel", value="channel"),
    app_commands.Choice(name="dm", value="dm"),
]


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

    @group.command(name="show", description="現在のMindStateを表示します")
    @app_commands.choices(scope=MIND_SCOPES)
    async def show(
        interaction: discord.Interaction,
        scope: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        kind = scope.value if scope else ("dm" if interaction.guild_id is None else "channel")
        target = _scope(interaction, kind)
        if target is None or not _allowed(interaction, kind, owner_id):
            await interaction.response.send_message("そのmindは、ここから開けないよ", ephemeral=True)
            return
        state = await storage.get(target)
        if state is None:
            await interaction.response.send_message(f"{target}\nまだ空だよ", ephemeral=True)
            return
        text = (
            f"{state.scope}\n{state.summary or '-'}\n"
            f"questions: {len(state.open_questions)} / active notes: {len(state.active_note_ids)}\n"
            f"updated: {state.updated_at}"
        )
        await interaction.response.send_message(text[:2000], ephemeral=True)

    @group.command(name="clear", description="現在のMindStateを消します")
    @app_commands.choices(scope=MIND_SCOPES)
    async def clear(
        interaction: discord.Interaction,
        scope: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        kind = scope.value if scope else ("dm" if interaction.guild_id is None else "channel")
        target = _scope(interaction, kind)
        if target is None or not _allowed(interaction, kind, owner_id):
            await interaction.response.send_message("そのmindは、ここから変えられないよ", ephemeral=True)
            return
        removed = await storage.clear(target)
        await interaction.response.send_message("mindを空にしたよ" if removed else "もともと空だよ", ephemeral=True)

    @group.command(name="status", description="現在地で利用するMindStateを表示します")
    async def status(interaction: discord.Interaction) -> None:
        scopes = ([f"dm:{interaction.user.id}", f"user:{interaction.user.id}"]
                  if interaction.guild_id is None else
                  [f"user:{interaction.user.id}", f"guild:{interaction.guild_id}",
                   f"channel:{interaction.channel_id}"])
        states = await storage.get_many(scopes)
        lines = ["mind state", *[f"{scope}: {'set' if any(s.scope == scope for s in states) else 'empty'}"
                                 for scope in scopes]]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    return group
