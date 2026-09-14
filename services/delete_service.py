
import asyncio
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from telethon.errors import FloodWaitError

@dataclass
class DeleteResult:
    found: int = 0
    deleted: int = 0
    skipped: int = 0
    errors: int = 0
    cancelled: bool = False

class DeleteService:
    def __init__(self, client):
        self.client = client
        self._jobs = {}

    def active(self, chat_id):
        return self._jobs.get(chat_id)

    def cancel(self, chat_id):
        job = self._jobs.get(chat_id)
        if job:
            job["cancel"] = True
            return True
        return False

    async def delete_recent_own(self, event, limit=None, since=None, progress=None):
        chat_id = event.chat_id
        if chat_id in self._jobs:
            raise RuntimeError("A deletion task is already running in this chat.")
        job = {"cancel": False}
        self._jobs[chat_id] = job
        result = DeleteResult()
        try:
            me = await self.client.get_me()
            candidates = []
            async for msg in self.client.iter_messages(event.chat_id, limit=limit):
                if since and msg.date < since:
                    break
                if msg.sender_id == me.id:
                    candidates.append(msg)
            result.found = len(candidates)
            total = max(1, result.found)
            for index, msg in enumerate(candidates, 1):
                if job["cancel"]:
                    result.cancelled = True
                    break
                try:
                    await self.client.delete_messages(event.chat_id, msg.id, revoke=True)
                    result.deleted += 1
                except FloodWaitError as exc:
                    await asyncio.sleep(exc.seconds)
                    try:
                        await self.client.delete_messages(event.chat_id, msg.id, revoke=True)
                        result.deleted += 1
                    except Exception:
                        result.errors += 1
                except Exception:
                    result.errors += 1
                if progress and (index == total or index % 5 == 0):
                    await progress(result, index, total)
            return result
        finally:
            self._jobs.pop(chat_id, None)

    @staticmethod
    def parse_period(token):
        now = datetime.now(timezone.utc)
        token = token.lower().strip()
        if token == "today":
            return None, datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        if len(token) >= 2 and token[-1] in ("m", "h") and token[:-1].isdigit():
            n = int(token[:-1])
            if n <= 0:
                raise ValueError("Time must be positive.")
            return None, now - timedelta(minutes=n) if token[-1] == "m" else now - timedelta(hours=n)
        raise ValueError("Unknown period.")
