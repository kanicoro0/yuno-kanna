from typing import Any, Dict, List

from yuno.mind.records import MindState


def build_mind_context(states: List[MindState]) -> Dict[str, Any]:
    return {
        "summaries": [{"scope": state.scope, "summary": state.summary} for state in states if state.summary][:3],
        "open_questions": list(dict.fromkeys(
            question for state in states for question in state.open_questions
        ))[:5],
        "active_note_ids": list(dict.fromkeys(
            note_id for state in states for note_id in state.active_note_ids
        ))[:10],
        "suppressed_note_ids": list(dict.fromkeys(
            note_id for state in states for note_id in state.suppressed_note_ids
        ))[:10],
        "tone_hints": list(dict.fromkeys(
            state.tone_hint for state in states if state.tone_hint
        ))[:3],
    }
