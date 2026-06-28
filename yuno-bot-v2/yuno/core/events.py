from collections import defaultdict
from dataclasses import dataclass, field
import logging
from typing import DefaultDict

import discord

from yuno.actions.executor import ActionExecutor
from yuno.actions.planner import Planner
from yuno.actions.speaker import Speaker
from yuno.conversation_log import ConversationLog
from yuno.core.preplanning import PrePlanner
from yuno.infra.discord_utils import add_reactions, classify_message, message_scopes
from yuno.mind.context import build_mind_context
from yuno.mind.storage import MindStateStorage
from yuno.notebook.prompt_view import planner_note_view
from yuno.notebook.retrieval import NotebookRetriever
from yuno.text import GENERIC_ERROR, RATE_LIMITED


logger = logging.getLogger(__name__)


@dataclass
class ConversationRuntime:
    planner: Planner
    executor: ActionExecutor
    speaker: Speaker
    retriever: NotebookRetriever
    preplanner: PrePlanner
    mind_storage: MindStateStorage
    conversation_logs: DefaultDict[int, ConversationLog] = field(
        default_factory=lambda: defaultdict(ConversationLog)
    )


def register_events(bot: discord.Client, runtime: ConversationRuntime) -> None:
    @bot.event
    async def on_ready() -> None:
        identity = str(bot.user) if bot.user else "unknown"
        print(f"Yuno v2 ready: {identity}")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        route = classify_message(message, bot.user)
        conversation_log = runtime.conversation_logs[message.channel.id]
        decision = await runtime.preplanner.decide(message, route)
        if not decision.should_plan:
            if route.context == "nonmention" and route.clean_content:
                conversation_log.append("user", route.clean_content)
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
        mind_scopes = (
            [f"dm:{message.author.id}", f"user:{message.author.id}"]
            if message.guild is None else
            [f"user:{message.author.id}", f"guild:{message.guild.id}",
             f"channel:{message.channel.id}"]
        )
        try:
            mind_context = build_mind_context(await runtime.mind_storage.get_many(mind_scopes))
            candidates = await runtime.retriever.retrieve(
                route_content, scopes, route.context,
                active_note_ids=mind_context["active_note_ids"],
                suppressed_note_ids=mind_context["suppressed_note_ids"],
            )
            plan = await runtime.planner.plan(
                route_content,
                route.context,
                scopes,
                conversation_log.planner_context(),
                planner_note_view(candidates),
                mind_context,
            )
            execution = await runtime.executor.prepare(plan, candidates, scopes)

            if not execution.should_speak:
                await add_reactions(message, execution.reactions)
                conversation_log.append("user", route_content)
                return

            conversation_context = conversation_log.speaker_context(plan.needs_log_lookup)
            async with message.channel.typing():
                speaker_output = await runtime.speaker.speak(
                    route_content, plan, execution, mind_context, conversation_context
                )
            sent = await message.reply(
                speaker_output.reply[:2000],
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )

            # Commit boundary: nothing persistent above this line changes notebook.
            system_reactions = await runtime.executor.commit(
                execution.pending_commits,
                actor_user_id=str(message.author.id),
                source="planner_commit",
            )
            if not speaker_output.mind_update.is_empty():
                primary_mind_scope = (
                    f"dm:{message.author.id}" if message.guild is None
                    else f"channel:{message.channel.id}"
                )
                await runtime.mind_storage.update(
                    primary_mind_scope, speaker_output.mind_update, str(message.id)
                )
            await add_reactions(message, execution.reactions + system_reactions)
            conversation_log.append("user", route_content)
            conversation_log.append("assistant", sent.content)

            if speaker_output.next_call.needed:
                # Schema is live, but a third model call / second message is intentionally deferred.
                logger.info("Optional third call requested but not implemented: %s", speaker_output.next_call.type)
        except Exception as error:
            logger.exception("Message pipeline failed (%s)", type(error).__name__)
            try:
                await message.reply(GENERIC_ERROR, mention_author=False)
            except discord.HTTPException:
                pass
