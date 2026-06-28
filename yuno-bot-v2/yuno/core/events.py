from collections import defaultdict
from dataclasses import asdict, dataclass, field
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
from yuno.debug.state import DebugState


logger = logging.getLogger(__name__)


@dataclass
class ConversationRuntime:
    planner: Planner
    executor: ActionExecutor
    speaker: Speaker
    retriever: NotebookRetriever
    preplanner: PrePlanner
    mind_storage: MindStateStorage
    debug: DebugState
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
        if await runtime.debug.handle_command(message, runtime.executor.storage):
            return
        # Ignore the bot's own sent reply without replacing the last user trace.
        if message.author.bot:
            return
        route = classify_message(message, bot.user)
        await runtime.debug.start_trace(
            message_id=str(message.id),
            author_id=str(message.author.id),
            channel_id=str(message.channel.id),
            guild_id=str(message.guild.id) if message.guild else None,
            route=route.context,
        )
        conversation_log = runtime.conversation_logs[message.channel.id]
        decision = await runtime.preplanner.decide(message, route)
        await runtime.debug.update_trace(
            should_reply=decision.should_plan,
            preplanning_result={"allowed": decision.should_plan, "reason": decision.reason},
            rate_limit_result=("blocked" if decision.reason == "rate_limited" else
                               "passed" if decision.should_plan else "not_checked"),
            sleep_result="blocked" if decision.reason == "sleeping" else "passed",
            autorespond_result=("blocked" if decision.reason == "nonmention_disabled" else
                                "passed" if route.context == "nonmention" else "not_applicable"),
        )
        if not decision.should_plan:
            if route.context == "nonmention" and route.clean_content:
                conversation_log.append("user", route.clean_content)
            if decision.notify_rate_limit:
                try:
                    await message.reply(RATE_LIMITED, mention_author=False)
                    await runtime.debug.update_trace(send_result="rate_limit_notice_sent")
                except discord.HTTPException:
                    await runtime.debug.update_trace(send_result="rate_limit_notice_failed")
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
            mind_states = await runtime.mind_storage.get_many(mind_scopes)
            mind_context = build_mind_context(mind_states)
            await runtime.debug.update_trace(
                mind_context_scopes=mind_scopes,
                recent_log_count=len(conversation_log.planner_context()),
                suppressed_note_ids=mind_context["suppressed_note_ids"],
            )
            candidates = await runtime.retriever.retrieve(
                route_content, scopes, route.context,
                active_note_ids=mind_context["active_note_ids"],
                suppressed_note_ids=mind_context["suppressed_note_ids"],
            )
            await runtime.debug.update_trace(note_candidate_count=len(candidates))
            plan = await runtime.planner.plan(
                route_content,
                route.context,
                scopes,
                conversation_log.planner_context(),
                planner_note_view(candidates),
                mind_context,
            )
            execution = await runtime.executor.prepare(plan, candidates, scopes)
            note_actions = [
                {
                    "action": action.note_action,
                    "scope": action.scope,
                    "target_note_id": action.target_note_id or None,
                }
                for action in plan.candidate_actions if action.type == "note"
            ]
            await runtime.debug.update_trace(
                should_reply=execution.should_speak,
                used_note_ids=[note.id for note in execution.selected_notes],
                needs_log_lookup=plan.needs_log_lookup,
                log_lookup_query=plan.log_lookup_query,
                speaker_note=plan.speaker_note,
                note_action=note_actions,
            )

            if not execution.should_speak:
                await add_reactions(message, execution.reactions)
                conversation_log.append("user", route_content)
                await runtime.debug.update_trace(send_result="not_requested")
                return

            conversation_context = conversation_log.speaker_context(plan.needs_log_lookup)
            await runtime.debug.update_trace(recent_log_count=len(conversation_context))
            async with message.channel.typing():
                speaker_output = await runtime.speaker.speak(
                    route_content, plan, execution, mind_context, conversation_context
                )
            sent = await message.reply(
                speaker_output.reply[:2000],
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await runtime.debug.update_trace(send_result="sent")

            # Commit boundary: nothing persistent above this line changes notebook.
            system_reactions = await runtime.executor.commit(
                execution.pending_commits,
                actor_user_id=str(message.author.id),
                source="planner_commit",
            )
            await runtime.debug.update_trace(notebook_commit_result={
                "success": True,
                "pending_count": len(execution.pending_commits),
                "committed_count": len(system_reactions),
            })
            primary_mind_scope = (
                f"dm:{message.author.id}" if message.guild is None
                else f"channel:{message.channel.id}"
            )
            mind_before = await runtime.mind_storage.get(primary_mind_scope)
            if not speaker_output.mind_update.is_empty():
                mind_after = await runtime.mind_storage.update(
                    primary_mind_scope, speaker_output.mind_update, str(message.id)
                )
                await runtime.debug.update_trace(mind_commit_result={
                    "success": True, "scope": primary_mind_scope,
                })
                await runtime.debug.capture_mind_diff(
                    primary_mind_scope, mind_before, mind_after,
                    asdict(speaker_output.mind_update), {"success": True},
                )
            else:
                await runtime.debug.update_trace(mind_commit_result={
                    "success": True, "updated": False, "reason": "empty mind_update",
                })
                await runtime.debug.capture_mind_diff(
                    primary_mind_scope, mind_before, None,
                    asdict(speaker_output.mind_update), {"success": True, "updated": False},
                    reason="Speaker returned an empty mind_update",
                )
            await add_reactions(message, execution.reactions + system_reactions)
            conversation_log.append("user", route_content)
            conversation_log.append("assistant", sent.content)

            if speaker_output.next_call.needed:
                # Schema is live, but a third model call / second message is intentionally deferred.
                logger.info("Optional third call requested but not implemented: %s", speaker_output.next_call.type)
        except Exception as error:
            await runtime.debug.add_error(error)
            logger.exception("Message pipeline failed (%s)", type(error).__name__)
            try:
                await message.reply(GENERIC_ERROR, mention_author=False)
            except discord.HTTPException:
                pass
