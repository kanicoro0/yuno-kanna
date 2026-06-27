"""Short, practical system text with a small amount of Yuno's voice."""


RATE_LIMITED = "……少しだけ待って"
GENERIC_ERROR = "うまく考えをまとめられなかった。少し置いて、もう一度呼んでね"
NO_MEMORIES = "ここには、まだ覚えていることはないみたい"


def memory_added(memory_id: str, scope: str) -> str:
    return f"覚えたよ\nID: `{memory_id}`\nscope: `{scope}`"


def memory_edited(memory_id: str, scope: str) -> str:
    return f"書き換えたよ\nID: `{memory_id}`\nscope: `{scope}`"


def memory_deleted(memory_id: str, scope: str) -> str:
    return f"その記憶は、そっと外したよ\nID: `{memory_id}`\nscope: `{scope}`"


def memory_not_found(memory_id: str) -> str:
    return f"その記憶は、ここでは見つからなかったよ\nID: `{memory_id}`"
