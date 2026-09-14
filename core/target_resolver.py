from dataclasses import dataclass
from telethon import TelegramClient
from telethon.tl.types import User

@dataclass(frozen=True)
class ResolvedTarget:
    user_id: int
    username: str | None
    display_name: str
    source: str

class TargetNotFound(Exception):
    pass

class TargetResolver:
    def __init__(self, client: TelegramClient):
        self.client = client

    async def resolve(self, event, explicit: str | None = None) -> ResolvedTarget:
        candidate = explicit.strip() if explicit else None

        if candidate:
            try:
                entity = await self.client.get_entity(candidate)
                return self._build(entity, "explicit")
            except Exception as exc:
                raise TargetNotFound(f"Target could not be resolved: {candidate}") from exc

        if event.is_reply:
            reply = await event.get_reply_message()
            if reply and reply.sender_id:
                entity = await self.client.get_entity(reply.sender_id)
                return self._build(entity, "reply")

        if event.is_private and event.chat_id:
            entity = await event.get_chat()
            return self._build(entity, "private_chat")

        raise TargetNotFound("No target could be determined safely.")

    def _build(self, entity, source: str) -> ResolvedTarget:
        if not isinstance(entity, User):
            raise TargetNotFound("Resolved entity is not a user.")
        name = " ".join(x for x in [entity.first_name, entity.last_name] if x).strip()
        return ResolvedTarget(
            user_id=entity.id,
            username=entity.username,
            display_name=name or str(entity.id),
            source=source,
        )
