from dataclasses import dataclass
import re
from typing import Iterable, Optional

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
        if is_listening and content:
            call_strength = call_name_strength(content, self.settings.yuno_call_names)
            if call_strength == "direct":
                return MessageRoute(True, True, content, "name_call", "plain")
            reason = "name_seen" if call_strength == "weak" else "listening_only"
            return MessageRoute(True, False, content, reason, "none")
        return _ignored()


def call_name_strength(content: str, call_names: Iterable[str]) -> Optional[str]:
    folded = content.casefold().strip()
    if not folded:
        return None
    best = None
    for name in call_names:
        candidate = name.casefold().strip()
        if not candidate:
            continue
        if candidate.isascii() and candidate.isalnum():
            if re.search(rf"(?<![a-z0-9]){re.escape(candidate)}(?![a-z0-9])", folded):
                return "direct"
            continue
        for match in re.finditer(re.escape(candidate), folded):
            before = folded[:match.start()].strip()
            after = folded[match.end():].strip()
            if _is_direct_japanese_call(before, after):
                return "direct"
            best = "weak"
    return best


def contains_call_name(content: str, call_names: Iterable[str]) -> bool:
    return call_name_strength(content, call_names) == "direct"


def _is_direct_japanese_call(before: str, after: str) -> bool:
    after = _strip_name_suffix(after)
    if not before and not after:
        return True
    if _ends_as_direct_lead(before) and not after:
        return True
    if _ends_as_direct_lead(before) and _starts_as_direct_tail(after):
        return True
    if not before and _starts_as_direct_tail(after):
        return True
    if _ends_with_boundary(before) and _starts_as_direct_tail(after):
        return True
    return False


def _strip_name_suffix(value: str) -> str:
    for suffix in ("ちゃん", "さん", "くん"):
        if value.startswith(suffix):
            return value[len(suffix):].strip()
    return value


def _ends_as_direct_lead(value: str) -> bool:
    if not value:
        return False
    if _ends_with_boundary(value):
        return True
    return any(value.endswith(prefix) for prefix in ("ねえ", "ねー", "おーい", "おい", "あの", "もしもし"))


def _starts_as_direct_tail(value: str) -> bool:
    if not value:
        return True
    if value[0] in "、，,.。!！?？〜~ー- ":
        return True
    return value.startswith((
        "おはよ", "おはよう", "おやすみ", "聞いて", "きいて",
        "教えて", "おしえて", "助けて", "たすけて", "いる", "いて",
        "ちょっと", "ねえ", "ねー",
    ))


def _ends_with_boundary(value: str) -> bool:
    return bool(value) and value[-1] in "、，,.。!！?？〜~ー- "


def _without_bot_mention(message: IncomingMessage) -> str:
    if not message.mentions_bot:
        return message.raw_content
    content = message.raw_content.replace(f"<@{message.bot_user_id}>", "")
    return content.replace(f"<@!{message.bot_user_id}>", "")


def _ignored() -> MessageRoute:
    return MessageRoute(False, False, "", "ignored", "none")
