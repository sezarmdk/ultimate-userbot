from dataclasses import dataclass
from enum import Enum

class ChatKind(str, Enum):
    PRIVATE = "private"
    GROUP = "group"
    CHANNEL = "channel"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class CommandContext:
    chat_id: int
    chat_kind: ChatKind
    is_reply: bool
    is_private: bool
    reply_sender_id: int | None = None
    current_user_id: int | None = None
