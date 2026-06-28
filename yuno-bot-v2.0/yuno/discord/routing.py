from dataclasses import dataclass

import discord

from yuno.config import Settings


@dataclass(frozen=True)
class MessageRoute:
    should_store: bool
    should_reply: bool
    clean_content: str


def route_message(
    message: discord.Message,
    bot_user: discord.ClientUser,
    settings: Settings,
) -> MessageRoute:
    is_dm = message.guild is None
    is_mention = bot_user in message.mentions
    is_listening = message.channel.id in settings.listening_channel_ids
    should_reply = is_dm or is_mention
    content = message.content
    if is_mention:
        content = content.replace(f"<@{bot_user.id}>", "")
        content = content.replace(f"<@!{bot_user.id}>", "")
    content = content.strip()
    if should_reply and not content:
        content = "呼びかけられた。"
    return MessageRoute(
        should_store=should_reply or is_listening,
        should_reply=should_reply,
        clean_content=content,
    )
