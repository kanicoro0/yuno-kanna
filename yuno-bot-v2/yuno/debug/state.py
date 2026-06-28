import asyncio
from copy import deepcopy
from dataclasses import asdict, is_dataclass
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from yuno.notebook.storage import NotebookStorage


logger = logging.getLogger(__name__)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _render_messages(messages: List[Dict[str, str]], metadata: Dict[str, Any]) -> str:
    sections = ["DEBUG METADATA", json.dumps(_jsonable(metadata), ensure_ascii=False, indent=2)]
    for message in messages:
        sections.extend((f"{str(message.get('role', 'unknown')).upper()} MESSAGE", str(message.get("content", ""))))
    return "\n\n".join(sections)


class DebugState:
    """Keeps one in-memory diagnostic snapshot; all failures are contained here."""

    PREFIX = "yuno-debug"

    def __init__(self, enabled: bool, owner_id: Optional[int], debug_dir: Path):
        self.enabled = enabled
        self.owner_id = owner_id
        self.debug_dir = debug_dir
        self._lock = asyncio.Lock()
        self.last_trace: Dict[str, Any] = {}
        self.last_planner_prompt = ""
        self.last_planner_output: Dict[str, Any] = {}
        self.last_speaker_prompt = ""
        self.last_speaker_output: Dict[str, Any] = {}
        self.last_mind_diff: Dict[str, Any] = {}
        self.last_cost: Dict[str, Any] = {}

    async def start_trace(self, **values: Any) -> None:
        if not self.enabled:
            return
        try:
            defaults = {
                "message_id": None, "author_id": None, "channel_id": None, "guild_id": None,
                "route": None, "mode": "planner_speaker", "should_reply": False,
                "preplanning_result": None, "rate_limit_result": "not_checked",
                "sleep_result": "not_checked", "autorespond_result": "not_checked",
                "mind_context_scopes": [], "recent_log_count": 0, "reply_tree_count": 0,
                "note_candidate_count": 0, "used_note_ids": [], "suppressed_note_ids": [],
                "needs_log_lookup": False, "log_lookup_query": None, "speaker_note": "",
                "note_action": [], "send_result": "not_attempted",
                "notebook_commit_result": "not_attempted", "mind_commit_result": "not_attempted",
                "errors": [],
            }
            defaults.update(_jsonable(values))
            async with self._lock:
                self.last_trace = defaults
                self.last_mind_diff = {"updated_scopes": [], "reason": "mind update was not reached"}
                self.last_cost = {
                    "planner_input_chars": 0, "planner_output_chars": 0,
                    "speaker_input_chars": 0, "speaker_output_chars": 0,
                    "mind_context_chars": 0, "recent_log_count": 0, "reply_tree_count": 0,
                    "note_candidate_count": 0, "notes_to_use_count": 0,
                    "mode": "planner_speaker", "needs_log_lookup": False,
                }
        except Exception:
            logger.warning("Debug trace initialization failed", exc_info=True)

    async def update_trace(self, **values: Any) -> None:
        if not self.enabled:
            return
        try:
            async with self._lock:
                self.last_trace.update(deepcopy(_jsonable(values)))
        except Exception:
            logger.warning("Debug trace update failed", exc_info=True)

    async def add_error(self, error: Exception) -> None:
        if not self.enabled:
            return
        # Keep errors useful without retaining provider payloads or environment values.
        summary = type(error).__name__
        try:
            async with self._lock:
                self.last_trace.setdefault("errors", []).append(summary)
        except Exception:
            logger.warning("Debug error capture failed", exc_info=True)

    async def capture_planner(
        self, messages: List[Dict[str, str]], output: Dict[str, Any], metadata: Dict[str, Any]
    ) -> None:
        if not self.enabled:
            return
        try:
            rendered = _render_messages(messages, metadata)
            output_data = deepcopy(_jsonable(output))
            output_text = json.dumps(output_data, ensure_ascii=False)
            async with self._lock:
                self.last_planner_prompt = rendered
                self.last_planner_output = output_data
                self.last_cost.update({
                    "planner_input_chars": len(rendered),
                    "planner_output_chars": len(output_text),
                    "mind_context_chars": len(json.dumps(metadata.get("mind_context", {}), ensure_ascii=False)),
                    "recent_log_count": int(metadata.get("recent_log_count", 0)),
                    "reply_tree_count": int(metadata.get("reply_tree_count", 0)),
                    "note_candidate_count": int(metadata.get("note_candidate_count", 0)),
                    "mode": str(metadata.get("mode", "planner_speaker")),
                })
        except Exception:
            logger.warning("Planner debug capture failed", exc_info=True)

    async def capture_speaker(
        self, messages: List[Dict[str, str]], output: Dict[str, Any], metadata: Dict[str, Any]
    ) -> None:
        if not self.enabled:
            return
        try:
            rendered = _render_messages(messages, metadata)
            output_data = deepcopy(_jsonable(output))
            output_text = json.dumps(output_data, ensure_ascii=False)
            async with self._lock:
                self.last_speaker_prompt = rendered
                self.last_speaker_output = output_data
                self.last_cost.update({
                    "speaker_input_chars": len(rendered),
                    "speaker_output_chars": len(output_text),
                    "recent_log_count": int(metadata.get("recent_log_count", 0)),
                    "reply_tree_count": int(metadata.get("reply_tree_count", 0)),
                    "notes_to_use_count": int(metadata.get("notes_to_use_count", 0)),
                    "mode": str(metadata.get("mode", "planner_speaker")),
                    "needs_log_lookup": bool(metadata.get("needs_log_lookup", False)),
                })
        except Exception:
            logger.warning("Speaker debug capture failed", exc_info=True)

    async def capture_mind_diff(
        self, scope: str, before: Any, after: Any, raw_update: Any,
        commit_result: Any, reason: str = "",
    ) -> None:
        if not self.enabled:
            return
        try:
            before_data = _jsonable(before.to_dict()) if before is not None else {}
            after_data = _jsonable(after.to_dict()) if after is not None else {}
            def changes(field: str) -> Dict[str, List[str]]:
                old, new = set(before_data.get(field, [])), set(after_data.get(field, []))
                return {"added": sorted(new - old), "removed": sorted(old - new)}
            diff = {
                "updated_scopes": [scope] if after is not None else [],
                "before_summary": before_data.get("summary", ""),
                "after_summary": after_data.get("summary", ""),
                "before_open_questions": before_data.get("open_questions", []),
                "after_open_questions": after_data.get("open_questions", []),
                "active_note_ids_changes": changes("active_note_ids"),
                "suppressed_note_ids_changes": changes("suppressed_note_ids"),
                "tone_hint_changes": {
                    "before": before_data.get("tone_hint", ""),
                    "after": after_data.get("tone_hint", ""),
                },
                "mind_update_raw": _jsonable(raw_update),
                "commit_result": _jsonable(commit_result),
                "reason": reason,
            }
            async with self._lock:
                self.last_mind_diff = diff
        except Exception:
            logger.warning("Mind debug capture failed", exc_info=True)

    async def handle_command(self, message: discord.Message, storage: "NotebookStorage") -> bool:
        content = str(getattr(message, "content", "")).strip()
        if not (content == self.PREFIX or content.startswith(self.PREFIX + " ")):
            return False
        if self.owner_id is None or getattr(message.author, "id", None) != self.owner_id:
            return True
        if not self.enabled:
            await self._reply(message, "debug disabled")
            return True
        parts = content.split()
        try:
            if parts[1:] == ["trace", "last"]:
                await self._write_json("last_trace.json", self.last_trace)
                await self._reply(message, f"last_trace.json / {len(self.last_trace.get('errors', []))} errors")
            elif parts[1:] == ["prompt", "last"]:
                await self._write_text("last_planner_prompt.txt", self.last_planner_prompt)
                await self._write_json("last_planner_output.json", self.last_planner_output)
                await self._write_text("last_speaker_prompt.txt", self.last_speaker_prompt)
                await self._write_json("last_speaker_output.json", self.last_speaker_output)
                await self._reply(message, "planner/speaker prompt + output saved (4 files)")
            elif parts[1:] == ["mind", "diff"]:
                await self._write_json("last_mind_diff.json", self.last_mind_diff)
                await self._reply(message, f"last_mind_diff.json / {len(self.last_mind_diff.get('updated_scopes', []))} updated")
            elif len(parts) == 4 and parts[1:3] == ["note", "find"]:
                result = await self._find_note(storage, parts[3], message)
                await self._write_json("last_note_find.json", result)
                state = result.get("state") or "missing"
                await self._reply(message, f"last_note_find.json / {result['resolved_note_id']} / {state}")
            elif parts[1:] == ["cost", "last"]:
                await self._write_json("last_cost.json", self.last_cost)
                await self._reply(message, "last_cost.json / character counts saved")
            else:
                await self._reply(message, "debug command not found")
        except Exception:
            logger.warning("Debug command failed", exc_info=True)
            await self._reply(message, "debug failed")
        return True

    async def _find_note(
        self, storage: "NotebookStorage", reference: str, message: discord.Message
    ) -> Dict[str, Any]:
        resolved = await storage.resolve_id(reference)
        canonical = f"note_{int(reference):04d}" if reference.isdigit() else reference
        note = await storage.get_by_id(resolved) if resolved else None
        allowed = {f"user:{message.author.id}"}
        if message.guild is not None:
            allowed.update({f"guild:{message.guild.id}", f"channel:{message.channel.id}"})
        if note is None:
            why = "note id was not found"
        elif note.state != "active":
            why = f"state is {note.state}"
        elif note.scope not in allowed:
            why = "outside the current user/server/channel view"
        else:
            why = "visible in the current view"
        return {
            "resolved_note_id": resolved or canonical,
            "exists": note is not None,
            "scope": note.scope if note else None,
            "state": note.state if note else None,
            "content_preview": note.content.replace("\n", " ")[:160] if note else "",
            "created_at": note.created_at if note else None,
            "updated_at": note.updated_at if note else None,
            "why_not_visible_if_possible": why,
        }

    async def _write_json(self, name: str, value: Any) -> None:
        text = json.dumps(_jsonable(value), ensure_ascii=False, indent=2) + "\n"
        await self._write_text(name, text)

    async def _write_text(self, name: str, value: str) -> None:
        def write() -> None:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            target = self.debug_dir / name
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_text(value, encoding="utf-8")
            temporary.replace(target)
        await asyncio.to_thread(write)

    @staticmethod
    async def _reply(message: discord.Message, text: str) -> None:
        try:
            await message.reply(
                text, mention_author=False, allowed_mentions=discord.AllowedMentions.none()
            )
        except Exception:
            logger.warning("Debug command reply failed", exc_info=True)
