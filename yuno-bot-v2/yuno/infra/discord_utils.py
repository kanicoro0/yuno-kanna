from dataclasses import dataclass
import re
from typing import List, Optional

import discord


PREFIXES = ("/yuno ", "!yuno ", "yuno. ")


@dataclass(frozen=True)
class MessageRoute:
    context: str
    should_plan: bool
    clean_content: str


def classify_message(message: discord.Message, bot_user: Optional[discord.ClientUser]) -> MessageRoute:
    content = message.content.strip()
    if message.guild is None:
        return MessageRoute("dm", True, content)

    if bot_user and bot_user in message.mentions:
        clean = re.sub(rf"<@!?{bot_user.id}>", "", content).strip()
        return MessageRoute("mention", True, clean)

    lowered = content.lower()
    for prefix in PREFIXES:
        if lowered.startswith(prefix):
            return MessageRoute("prefix", True, content[len(prefix):].strip())

    # Non-mention observation is intentionally passive in the initial skeleton.
    return MessageRoute("nonmention", False, content)


def message_scopes(message: discord.Message) -> List[str]:
    scopes = [f"user:{message.author.id}"]
    if message.guild:
        scopes.append(f"guild:{message.guild.id}")
        scopes.append(f"channel:{message.channel.id}")
    return scopes


async def add_reactions(message: discord.Message, reactions: List[str]) -> None:
    for emoji in dict.fromkeys(reactions):
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            # A failed reaction must not turn a successful reply into a failure.
            continue
