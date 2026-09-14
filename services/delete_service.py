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
    scanned: int = 0


class DeleteService:
    def __init__(self, client):
        self.client = client
        self._jobs = {}

    def active(self, chat_id):
        return self._jobs.get(chat_id)

    def cancel(self, chat_id):
        job = self._jobs.get(chat_id)
        if not job:
            return False
        job["cancel"] = True
        return True

    async def delete_recent_own(self, event, limit=None, since=None, progress=None, exclude_ids=None):
        chat_id = event.chat_id
        if chat_id in self._jobs:
            raise RuntimeError("Bu chatda o‘chirish jarayoni allaqachon ishlamoqda.")

        job = {"cancel": False}
        self._jobs[chat_id] = job
        result = DeleteResult()
        event_id = getattr(event, "id", None) or getattr(getattr(event, "message", None), "id", None)
        excluded = set(exclude_ids or ())
        if event_id is not None:
            excluded.add(event_id)

        try:
            me = await self.client.get_me()
            me_id = getattr(me, "id", None)
            if me_id is None:
                raise RuntimeError("Telegram akkaunti aniqlanmadi.")

            candidates = []
            # Hard upper bound prevents an accidental endless scan in huge chats.
            requested = limit or 100
            # Requested own-message count needs a wider scan window, but never unlimited.
            base_scan_limit = max(requested * 50, 500)
            scan_limit = min(base_scan_limit, 20000) if limit else 20000
            async for msg in self.client.iter_messages(chat_id, limit=scan_limit):
                result.scanned += 1
                msg_date = msg.date
                if msg_date and msg_date.tzinfo is None:
                    msg_date = msg_date.replace(tzinfo=timezone.utc)
                if since and msg_date and msg_date < since:
                    break
                if msg.id in excluded:
                    result.skipped += 1
                    continue
                if msg.sender_id == me_id:
                    candidates.append(msg)
                    if limit and len(candidates) >= limit:
                        break

            result.found = len(candidates)
            total = max(1, result.found)
            for index, msg in enumerate(candidates, 1):
                if job["cancel"]:
                    result.cancelled = True
                    break
                try:
                    await self.client.delete_messages(chat_id, msg.id, revoke=True)
                    result.deleted += 1
                except FloodWaitError as exc:
                    await asyncio.sleep(exc.seconds)
                    try:
                        await self.client.delete_messages(chat_id, msg.id, revoke=True)
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
                raise ValueError("Vaqt 0 dan katta bo‘lishi kerak.")
            return None, now - (timedelta(minutes=n) if token[-1] == "m" else timedelta(hours=n))
        raise ValueError("Vaqt formati tushunilmadi. Masalan: 30m, 1h yoki today.")
