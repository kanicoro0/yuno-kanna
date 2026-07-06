"""Short, practical system text with a small amount of Yuno's voice."""


RATE_LIMITED = "……少しだけ待って"
GENERIC_ERROR = "うまく考えをまとめられなかった。少し置いて、もう一度呼んでね"
NO_NOTES = "ここには、まだ覚えていることはないみたい"


def note_added(note_id: str, scope: str) -> str:
    return f"覚えたよ\nID: `{note_id}`\n対象: `{scope}`"


def note_edited(note_id: str, scope: str) -> str:
    return f"書き換えたよ\nID: `{note_id}`\n対象: `{scope}`"


def note_deleted(note_id: str, scope: str) -> str:
    return f"そのnoteは、そっと外したよ\nID: `{note_id}`\n対象: `{scope}`"


def note_not_found(note_id: str) -> str:
    return f"そのnoteは、ここでは見つからなかったよ\nID: `{note_id}`"
