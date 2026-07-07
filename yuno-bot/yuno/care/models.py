from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class CareMarkCandidate:
    kind: str
    status: str
    text: str
    confidence: float = 0.5
    sensitive: bool = False
    about_other_person: bool = False


@dataclass(frozen=True)
class ReadCueUpdate:
    term: str
    weight: float
    care_mark_public_id: Optional[str] = None
    candidate_text: Optional[str] = None


@dataclass(frozen=True)
class CareReadRequest:
    current_message: str
    recent_messages: Tuple[Dict[str, str], ...]
    care_marks: Tuple[Dict[str, Any], ...]
    read_cues: Tuple[Dict[str, Any], ...]
    addressing_strength: float
    cue_salience: float
    route_reason: str = ''
    reply_mode: str = 'none'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'current_message': self.current_message,
            'recent_messages': list(self.recent_messages),
            'care_marks': list(self.care_marks),
            'read_cues': list(self.read_cues),
            'addressing_strength': self.addressing_strength,
            'cue_salience': self.cue_salience,
            'route_reason': self.route_reason,
            'reply_mode': self.reply_mode,
        }


@dataclass(frozen=True)
class CareReadResult:
    decision_made: bool = False
    wants_to_speak: bool = False
    should_speak: bool = False
    reply_reason: str = ''
    speaker_note: str = ''
    care_mark_candidates: Tuple[CareMarkCandidate, ...] = ()
    read_cue_updates: Tuple[ReadCueUpdate, ...] = ()
    touch_care_mark_ids: Tuple[str, ...] = ()
    include_care_mark_ids: Tuple[str, ...] = ()
