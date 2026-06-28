from typing import Optional

import discord

from yuno.messages import IncomingMessage


def to_incoming_message(
    message: discord.Message,
    bot_user: discord.ClientUser,
) -> IncomingMessage:
    reply_to: Optional[str] = None
    if message.reference and message.reference.message_id:
        reply_to = str(message.reference.message_id)
    return IncomingMessage(
        discord_message_id=str(message.id),
        discord_channel_id=str(message.channel.id),
        discord_guild_id=str(message.guild.id) if message.guild else None,
        stream_kind="dm" if message.guild is None else "channel",
        author_id=str(message.author.id),
        author_name=message.author.display_name,
        author_is_bot=message.author.bot,
        bot_user_id=str(bot_user.id),
        mentions_bot=bot_user in message.mentions,
        raw_content=message.content,
        created_at=message.created_at.isoformat(),
        reply_to_discord_message_id=reply_to,
    )
