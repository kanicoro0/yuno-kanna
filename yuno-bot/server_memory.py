import discord

from config import OWNER_ID


guild_notes = {}
save_guild_notes = None


def configure(*, notes, save_notes):
    global guild_notes, save_guild_notes
    guild_notes = notes
    save_guild_notes = save_notes


servermemory_group = discord.app_commands.Group(
    name="servermemory",
    description="このサーバーのメモを表示・編集します",
)

@servermemory_group.command(name="show", description="このサーバーのメモを表示します")
@discord.app_commands.guild_only()
async def servermemory_show(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "⚠️ サーバーでのみ使用できるみたい",
            ephemeral=True,
        )
        return
    note = guild_notes.get(
        str(interaction.guild.id),
        "……この場所のこと、まだなにも書いてないみたい",
    )
    await interaction.response.send_message(
        f"🏠 このサーバーのメモ：{note}",
        ephemeral=True,
    )

@servermemory_group.command(name="set", description="このサーバーのメモを更新します")
@discord.app_commands.guild_only()
@discord.app_commands.describe(content="サーバーメモの内容（200文字以内）")
async def servermemory_set(interaction: discord.Interaction, content: str):
    if interaction.guild is None:
        await interaction.response.send_message(
            "⚠️ サーバーでのみ使用できるみたい",
            ephemeral=True,
        )
        return
    permissions = getattr(interaction.user, "guild_permissions", None)
    can_manage_guild = bool(getattr(permissions, "manage_guild", False))
    if str(interaction.user.id) != OWNER_ID and not can_manage_guild:
        await interaction.response.send_message(
            "⚠️ サーバーメモの更新は管理できる人だけにしているよ",
            ephemeral=True,
        )
        return
    stripped_content = content.strip()
    if not stripped_content:
        await interaction.response.send_message(
            "⚠️ 空のメモは保存できないみたい",
            ephemeral=True,
        )
        return
    if len(stripped_content) > 200:
        await interaction.response.send_message(
            "⚠️ メモは200文字以内でお願い",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True)
    guild_notes[str(interaction.guild.id)] = stripped_content
    await save_guild_notes()
    await interaction.followup.send(
        f"📝 サーバーメモを更新したよ：{stripped_content}",
        ephemeral=True,
    )
