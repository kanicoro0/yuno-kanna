import asyncio
from collections import deque
from dataclasses import dataclass
import time
from typing import Deque, Dict, Optional

import discord

from yuno.infra.discord_utils import MessageRoute
from yuno.runtime.settings import RuntimeSettings


@dataclass(frozen=True)
class PrePlanningDecision:
    should_plan: bool
    notify_rate_limit: bool = False
    reason: str = ""


class RateLimiter:
    USER_COOLDOWN_SECONDS = 10.0
    CHANNEL_COOLDOWN_SECONDS = 5.0
    GLOBAL_WINDOW_SECONDS = 60.0
    GLOBAL_MAX_REQUESTS = 20

    def __init__(self):
        self._users: Dict[int, float] = {}
        self._channels: Dict[int, float] = {}
        self._global: Deque[float] = deque()
        self._lock = asyncio.Lock()

    async def allow(self, user_id: int, channel_id: int) -> bool:
        now = time.monotonic()
        async with self._lock:
            cutoff = now - self.GLOBAL_WINDOW_SECONDS
            while self._global and self._global[0] <= cutoff:
                self._global.popleft()
            if now - self._users.get(user_id, float("-inf")) < self.USER_COOLDOWN_SECONDS:
                return False
            if now - self._channels.get(channel_id, float("-inf")) < self.CHANNEL_COOLDOWN_SECONDS:
                return False
            if len(self._global) >= self.GLOBAL_MAX_REQUESTS:
                return False
            self._users[user_id] = now
            self._channels[channel_id] = now
            self._global.append(now)
            return True


class PrePlanner:
    def __init__(self, settings: RuntimeSettings, rate_limiter: Optional[RateLimiter] = None):
        self.settings = settings
        self.rate_limiter = rate_limiter or RateLimiter()

    async def decide(self, message: discord.Message, route: MessageRoute) -> PrePlanningDecision:
        if message.author.bot:
            return PrePlanningDecision(False, reason="bot_author")
        guild_id = message.guild.id if message.guild else None
        channel_id = message.channel.id
        if await self.settings.is_sleeping(guild_id, channel_id):
            return PrePlanningDecision(False, reason="sleeping")

        is_direct = route.context in {"dm", "mention", "prefix"}
        if route.context == "nonmention":
            if not await self.settings.auto_reply_allowed(guild_id, channel_id):
                return PrePlanningDecision(False, reason="nonmention_disabled")
        elif not is_direct:
            return PrePlanningDecision(False, reason="unsupported_route")

        if not await self.rate_limiter.allow(message.author.id, channel_id):
            return PrePlanningDecision(False, notify_rate_limit=is_direct, reason="rate_limited")
        return PrePlanningDecision(True, reason="allowed")
