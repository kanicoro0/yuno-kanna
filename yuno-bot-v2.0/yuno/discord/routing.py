from dataclasses import dataclass
import re
from typing import Iterable

from yuno.config import Settings
from yuno.conversation.repository import ConversationRepository
from yuno.listening.service import ListeningChannelService
from yuno.messages import IncomingMessage


@dataclass(frozen=True)
class MessageRoute:
    should_store: bool
    should_reply: bool
    speaker_content: str
    reason: str
    reply_mode: str


class MessageRouter:
    def __init__(
        self, settings: Settings, repository: ConversationRepository,
        listening: ListeningChannelService = None,
    ):
        self.settings = settings
        self.repository = repository
        self.listening = listening

    async def route(self, message: IncomingMessage) -> MessageRoute:
        if message.author_is_bot:
            return _ignored()

        is_dm = message.stream_kind == "dm"
        is_listening = (
            await self.listening.is_listening(message.discord_channel_id)
            if self.listening else
            int(message.discord_channel_id) in self.settings.listening_channel_ids
        )
        reply_to_yuno = await self.repository.is_assistant_message(
            message.reply_to_discord_message_id
        )
        content = _without_bot_mention(message).strip()

        if is_dm:
            if not content:
                return _ignored()
            return MessageRoute(True, True, content, "dm", "plain")
        if message.mentions_bot:
            return MessageRoute(
                True,
                True,
                content or self.settings.yuno_call_names[0],
                "mention",
                "discord_reply",
            )
        if reply_to_yuno:
            if not content:
                return _ignored()
            return MessageRoute(True, True, content, "reply_to_yuno", "discord_reply")
        if is_listening and content and contains_call_name(
            content, self.settings.yuno_call_names
        ):
            return MessageRoute(True, True, content, "name_call", "plain")
        if is_listening and content:
            return MessageRoute(True, False, content, "listening_only", "none")
        return _ignored()


def contains_call_name(content: str, call_names: Iterable[str]) -> bool:
    folded = content.casefold()
    for name in call_names:
        candidate = name.casefold().strip()
        if not candidate:
            continue
        if candidate.isascii() and candidate.isalnum():
            if re.search(rf"(?<![a-z0-9]){re.escape(candidate)}(?![a-z0-9])", folded):
                return True
        elif candidate in folded:
            return True
    return False


def _without_bot_mention(message: IncomingMessage) -> str:
    if not message.mentions_bot:
        return message.raw_content
    content = message.raw_content.replace(f"<@{message.bot_user_id}>", "")
    return content.replace(f"<@!{message.bot_user_id}>", "")


def _ignored() -> MessageRoute:
    return MessageRoute(False, False, "", "ignored", "none")
