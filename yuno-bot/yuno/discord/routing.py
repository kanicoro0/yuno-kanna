from dataclasses import dataclass
from datetime import datetime
import re
from typing import Iterable, Optional

from yuno.config import Settings
from yuno.conversation.repository import ConversationRepository
from yuno.listening.service import ListeningChannelService
from yuno.messages import IncomingMessage


RECENT_YUNO_FOLLOWUP_SECONDS = 10 * 60


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
            if await self._is_recent_yuno_followup(message, content):
                return MessageRoute(True, True, content, "recent_yuno_followup", "plain")
            reason = "name_seen" if call_strength == "weak" else "listening_only"
            return MessageRoute(True, False, content, reason, "none")
        return _ignored()

    async def _is_recent_yuno_followup(
        self,
        message: IncomingMessage,
        content: str,
    ) -> bool:
        if not _looks_like_followup(content):
            return False
        stream = await self.repository.get_stream_by_channel_id(
            message.discord_channel_id
        )
        if stream is None:
            return False
        recent = await self.repository.recent(stream.id, 3)
        if not recent or recent[-1].role != "assistant":
            return False
        return _seconds_between(
            recent[-1].created_at,
            message.created_at,
        ) <= RECENT_YUNO_FOLLOWUP_SECONDS


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
    if _ends_as_direct_lead(before) and _looks_like_question(after):
        return True
    if not before and _starts_as_direct_tail(after):
        return True
    if not before and _looks_like_question(after):
        return True
    if _ends_with_boundary(before) and _starts_as_direct_tail(after):
        return True
    if _ends_with_boundary(before) and _looks_like_question(after):
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
        "起き", "おき", "返事", "返信", "反応", "できる", "できない",
        "ちょっと", "ねえ", "ねー",
    ))


def _looks_like_followup(content: str) -> bool:
    value = content.strip()
    if not value:
        return False
    if _looks_like_question(value):
        return True
    return value.startswith((
        "それ", "これ", "じゃあ", "じゃ", "でも", "あと", "なら",
        "うん", "いや", "え", "ん", "つまり",
    ))


def _looks_like_question(value: str) -> bool:
    return "?" in value or "？" in value


def _seconds_between(older: str, newer: str) -> float:
    older_time = _parse_created_at(older)
    newer_time = _parse_created_at(newer)
    if older_time is None or newer_time is None:
        return RECENT_YUNO_FOLLOWUP_SECONDS + 1
    return (newer_time - older_time).total_seconds()


def _parse_created_at(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _ends_with_boundary(value: str) -> bool:
    return bool(value) and value[-1] in "、，,.。!！?？〜~ー- "


def _without_bot_mention(message: IncomingMessage) -> str:
    if not message.mentions_bot:
        return message.raw_content
    content = message.raw_content.replace(f"<@{message.bot_user_id}>", "")
    return content.replace(f"<@!{message.bot_user_id}>", "")


def _ignored() -> MessageRoute:
    return MessageRoute(False, False, "", "ignored", "none")
