from dataclasses import dataclass
from urllib.parse import urlparse
from telethon import TelegramClient
from telethon.tl.types import User

@dataclass(frozen=True)
class ResolvedTarget:
    user_id: int
    username: str | None
    display_name: str
    source: str
    entity: object

class TargetNotFound(Exception):
    pass

class TargetResolver:
    def __init__(self, client: TelegramClient):
        self.client = client

    @staticmethod
    def normalize(candidate: str) -> str | int:
        value = candidate.strip()
        if value.startswith(('https://t.me/', 'http://t.me/', 'https://telegram.me/', 'http://telegram.me/')):
            path = urlparse(value).path.strip('/')
            if not path or '/' in path:
                raise TargetNotFound("Telegram havolasidan foydalanuvchi aniqlanmadi.")
            value = '@' + path
        if value.startswith('tg://resolve?domain='):
            value = '@' + value.split('=', 1)[1].split('&', 1)[0]
        if value.lstrip('-').isdigit():
            return int(value)
        return value if value.startswith('@') else '@' + value

    async def resolve(self, event, explicit: str | None = None) -> ResolvedTarget:
        candidate = self.normalize(explicit) if explicit and explicit.strip() else None
        if candidate is not None:
            try:
                entity = await self.client.get_entity(candidate)
                return self._build(entity, "explicit")
            except TargetNotFound:
                raise
            except Exception as exc:
                raise TargetNotFound(f"Foydalanuvchi aniqlanmadi: {explicit}") from exc

        if event.is_reply:
            reply = await event.get_reply_message()
            if reply and reply.sender_id:
                try:
                    entity = await self.client.get_entity(reply.sender_id)
                    return self._build(entity, "reply")
                except Exception as exc:
                    raise TargetNotFound("Javob berilgan xabar egasi aniqlanmadi.") from exc

        if event.is_private and event.chat_id:
            try:
                entity = await event.get_chat()
                return self._build(entity, "private_chat")
            except Exception as exc:
                raise TargetNotFound("Shaxsiy suhbatdagi foydalanuvchi aniqlanmadi.") from exc

        raise TargetNotFound("Foydalanuvchini xavfsiz aniqlab bo‘lmadi.")

    def _build(self, entity, source: str) -> ResolvedTarget:
        if not isinstance(entity, User):
            raise TargetNotFound("Aniqlangan obyekt foydalanuvchi emas.")
        name = " ".join(x for x in [entity.first_name, entity.last_name] if x).strip()
        return ResolvedTarget(
            user_id=entity.id, username=entity.username,
            display_name=name or entity.username or str(entity.id),
            source=source, entity=entity,
        )
