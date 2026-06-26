from typing import Optional

import discord
from discord import app_commands

from config import DISCORD_LIMIT, OWNER_ID


settings = {}
settings_file = None
write_json_async = None
safe_report_error = print


def configure(*, settings_store, file_path, write_json, error_reporter):
    global settings, settings_file, write_json_async, safe_report_error
    settings = settings_store
    settings_file = file_path
    write_json_async = write_json
    safe_report_error = error_reporter
    _ensure_shape()


def _ensure_shape():
    if not isinstance(settings.get("guilds"), dict):
        settings["guilds"] = {}
    settings["global_sleep"] = bool(settings.get("global_sleep", False))


def _guild_settings(guild_id):
    _ensure_shape()
    guild_id = str(guild_id)
    guild = settings["guilds"].setdefault(guild_id, {})
    if "auto_reply_enabled" not in guild:
        guild["auto_reply_enabled"] = True
    if not isinstance(guild.get("disabled_channels"), dict):
        guild["disabled_channels"] = {}
    return guild


async def persist_settings():
    if write_json_async is None or settings_file is None:
        return
    try:
        _ensure_shape()
        await write_json_async(settings_file, settings)
    except Exception as error:
        safe_report_error(f"自動返信設定の保存に失敗: {error}")


def is_global_sleeping():
    _ensure_shape()
    return settings.get("global_sleep") is True


async def set_global_sleep(enabled):
    _ensure_shape()
    settings["global_sleep"] = bool(enabled)
    await persist_settings()


def guild_auto_reply_enabled(guild_id):
    return _guild_settings(guild_id).get("auto_reply_enabled") is not False


def channel_auto_reply_enabled(guild_id, channel_id):
    guild = _guild_settings(guild_id)
    disabled = guild.get("disabled_channels", {})
    return str(channel_id) not in disabled


def should_auto_reply_in_channel(message):
    if message.guild is None:
        return True
    guild_id = str(message.guild.id)
    channel_id = str(message.channel.id)
    return guild_auto_reply_enabled(guild_id) and channel_auto_reply_enabled(
        guild_id,
        channel_id,
    )


async def set_guild_auto_reply(guild_id, enabled):
    guild = _guild_settings(guild_id)
    guild["auto_reply_enabled"] = bool(enabled)
    await persist_settings()


async def set_channel_auto_reply(guild_id, channel_id, enabled):
    guild = _guild_settings(guild_id)
    disabled = guild.setdefault("disabled_channels", {})
    channel_id = str(channel_id)
    if enabled:
        disabled.pop(channel_id, None)
    else:
        disabled[channel_id] = True
    await persist_settings()


def _is_owner(user):
    return str(getattr(user, "id", "")) == str(OWNER_ID)


def _has_any_guild_permission(member, *permission_names):
    permissions = getattr(member, "guild_permissions", None)
    if permissions is None:
        return False
    return any(bool(getattr(permissions, name, False)) for name in permission_names)


def _can_manage_guild(interaction):
    return (
        _is_owner(interaction.user)
        or _has_any_guild_permission(
            interaction.user,
            "administrator",
            "manage_guild",
        )
    )


def _can_manage_channel(interaction, channel):
    if _is_owner(interaction.user) or _can_manage_guild(interaction):
        return True
    permissions_for = getattr(channel, "permissions_for", None)
    if permissions_for is None:
        return _has_any_guild_permission(
            interaction.user,
            "administrator",
            "manage_channels",
        )
    permissions = permissions_for(interaction.user)
    return bool(
        getattr(permissions, "administrator", False)
        or getattr(permissions, "manage_channels", False)
    )


def _require_guild(interaction):
    return interaction.guild is not None


def _mode_to_bool(mode):
    mode = str(mode or "").strip().lower()
    if mode == "on":
        return True
    if mode == "off":
        return False
    return None


def _status_lines(guild, channel):
    guild_id = str(guild.id)
    channel_id = str(channel.id)
    guild_enabled = guild_auto_reply_enabled(guild_id)
    channel_enabled = channel_auto_reply_enabled(guild_id, channel_id)
    effective = guild_enabled and channel_enabled
    disabled_count = len(_guild_settings(guild_id).get("disabled_channels", {}))
    return [
        "🫧 自動返信設定",
        f"・サーバー全体: {'ON' if guild_enabled else 'OFF'}",
        f"・このチャンネル: {'ON' if channel_enabled else 'OFF'}",
        f"・実際の通常自動返信: {'ON' if effective else 'OFF'}",
        f"・OFFにしているチャンネル数: {disabled_count}",
        "",
        "※メンション時はこの設定に関係なく返すよ",
        "※/yuno sleep 中はメンションも含めてコマンド以外を止めるよ",
    ]


autorespond_group = app_commands.Group(
    name="autorespond",
    description="通常自動返信のON/OFFを設定します",
)


@autorespond_group.command(
    name="status",
    description="このサーバーとチャンネルの通常自動返信設定を表示します",
)
async def slash_autorespond_status(interaction):
    if not _require_guild(interaction):
        await interaction.response.send_message(
            "この設定はサーバー内だけで使えるよ",
            ephemeral=True,
        )
        return
    lines = _status_lines(interaction.guild, interaction.channel)
    await interaction.response.send_message(
        "\n".join(lines)[:DISCORD_LIMIT],
        ephemeral=True,
    )


@autorespond_group.command(
    name="server",
    description="サーバー全体の通常自動返信をON/OFFします",
)
@app_commands.choices(mode=[
    app_commands.Choice(name="on", value="on"),
    app_commands.Choice(name="off", value="off"),
])
async def slash_autorespond_server(interaction, mode: app_commands.Choice[str]):
    if not _require_guild(interaction):
        await interaction.response.send_message(
            "この設定はサーバー内だけで使えるよ",
            ephemeral=True,
        )
        return
    if not _can_manage_guild(interaction):
        await interaction.response.send_message(
            "サーバー全体の設定は、サーバー管理権限がある人だけが使えるよ",
            ephemeral=True,
        )
        return
    enabled = _mode_to_bool(mode.value)
    await set_guild_auto_reply(interaction.guild.id, enabled)
    await interaction.response.send_message(
        f"サーバー全体の通常自動返信を{'ON' if enabled else 'OFF'}にしたよ",
        ephemeral=True,
    )


@autorespond_group.command(
    name="channel",
    description="チャンネル単位の通常自動返信をON/OFFします",
)
@app_commands.choices(mode=[
    app_commands.Choice(name="on", value="on"),
    app_commands.Choice(name="off", value="off"),
])
async def slash_autorespond_channel(
    interaction,
    mode: app_commands.Choice[str],
    channel: Optional[discord.TextChannel] = None,
):
    if not _require_guild(interaction):
        await interaction.response.send_message(
            "この設定はサーバー内だけで使えるよ",
            ephemeral=True,
        )
        return
    target_channel = channel or interaction.channel
    if not _can_manage_channel(interaction, target_channel):
        await interaction.response.send_message(
            "チャンネル単位の設定は、チャンネル管理権限がある人だけが使えるよ",
            ephemeral=True,
        )
        return
    enabled = _mode_to_bool(mode.value)
    await set_channel_auto_reply(interaction.guild.id, target_channel.id, enabled)
    mention = getattr(target_channel, "mention", f"#{target_channel}")
    await interaction.response.send_message(
        f"{mention} の通常自動返信を{'ON' if enabled else 'OFF'}にしたよ",
        ephemeral=True,
    )
