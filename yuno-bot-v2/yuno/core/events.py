from collections import defaultdict, deque
from dataclasses import dataclass, field
import logging
from typing import Deque, Dict, List

import discord

from yuno.actions.executor import ActionExecutor
from yuno.actions.planner import Planner
from yuno.actions.speaker import Speaker
from yuno.core.preplanning import PrePlanner
from yuno.infra.discord_utils import add_reactions, classify_message, message_scopes
from yuno.memory.prompt_view import planner_memory_view
from yuno.memory.retrieval import MemoryRetriever
from yuno.text import GENERIC_ERROR, RATE_LIMITED


logger = logging.getLogger(__name__)


@dataclass
class ConversationRuntime:
    planner: Planner
    executor: ActionExecutor
    speaker: Speaker
    retriever: MemoryRetriever
    preplanner: PrePlanner
    histories: Dict[int, Deque[Dict[str, str]]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=24))
    )


def register_events(bot: discord.Client, runtime: ConversationRuntime) -> None:
    @bot.event
    async def on_ready() -> None:
        identity = str(bot.user) if bot.user else "unknown"
        print(f"Yuno v2 ready: {identity}")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        route = classify_message(message, bot.user)
        history = runtime.histories[message.channel.id]
        decision = await runtime.preplanner.decide(message, route)
        if not decision.should_plan:
            if route.context == "nonmention" and route.clean_content:
                history.append({"role": "user", "content": route.clean_content[:2000]})
            if decision.notify_rate_limit:
                try:
                    await message.reply(RATE_LIMITED, mention_author=False)
                except discord.HTTPException:
                    pass
            return
        if not route.clean_content:
            route_content = "呼びかけられた。"
        else:
            route_content = route.clean_content

        scopes = message_scopes(message)
        try:
            candidates = await runtime.retriever.retrieve(
                route_content, scopes, route.context
            )
            plan = await runtime.planner.plan(
                route_content,
                route.context,
                scopes,
                list(history),
                planner_memory_view(candidates),
            )
            execution = await runtime.executor.prepare(plan, candidates, scopes)

            if not execution.should_speak:
                await add_reactions(message, execution.reactions)
                history.append({"role": "user", "content": route_content[:2000]})
                return

            async with message.channel.typing():
                speaker_output = await runtime.speaker.speak(route_content, plan, execution)
            sent = await message.reply(
                speaker_output.reply[:2000],
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )

            # Commit boundary: nothing persistent above this line changes memory.
            system_reactions = await runtime.executor.commit(
                execution.pending_commits,
                actor_user_id=str(message.author.id),
                source="planner_commit",
            )
            await add_reactions(message, execution.reactions + system_reactions)
            history.append({"role": "user", "content": route_content[:2000]})
            history.append({"role": "assistant", "content": sent.content[:2000]})

            if speaker_output.next_call.needed:
                # Schema is live, but a third model call / second message is intentionally deferred.
                logger.info("Optional third call requested but not implemented: %s", speaker_output.next_call.type)
        except Exception as error:
            logger.exception("Message pipeline failed (%s)", type(error).__name__)
            try:
                await message.reply(GENERIC_ERROR, mention_author=False)
            except discord.HTTPException:
                pass
