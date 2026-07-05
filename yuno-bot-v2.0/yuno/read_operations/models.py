from dataclasses import dataclass
from enum import Enum


class ReadSource(str, Enum):
    CURRENT_STREAM = 'current_stream'
    CONVERSATION_LOG = 'conversation_log'
    CARE_MARKS = 'care_marks'


class ReadRange(str, Enum):
    LAST_N = 'last_n'
    TODAY = 'today'
    YESTERDAY = 'yesterday'
    AROUND_DATE = 'around_date'


class ReadPurpose(str, Enum):
    SUMMARIZE = 'summarize'
    FIND_OPEN = 'find_open'
    CONTINUE_TOPIC = 'continue_topic'


class ReadPersistence(str, Enum):
    REPLY_ONLY = 'reply_only'
    TOUCH_CARE_MARKS = 'touch_care_marks'


@dataclass(frozen=True)
class ReadOperation:
    source: ReadSource
    range: ReadRange
    purpose: ReadPurpose
    persistence: ReadPersistence
    last_n: int = 10


@dataclass(frozen=True)
class ReadOperationResult:
    range_read: str
    summary_input: str
    message_count: int

    @property
    def is_empty(self) -> bool:
        return self.message_count == 0


class UnsupportedReadOperation(ValueError):
    pass
