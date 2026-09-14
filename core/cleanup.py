from collections import defaultdict, deque


class ResponseCleanup:
    """Keeps only the latest deletable interface responses per chat.

    Failed Telegram deletions are retained in memory/database so a later response
    can retry them instead of silently losing cleanup state.
    """
    NON_DELETABLE_TYPES = {"progress", "persistent", "critical", "log"}

    def __init__(self, client, history_service=None, limit: int = 2):
        if limit < 1:
            raise ValueError("cleanup limit must be at least 1")
        self.client = client
        self.history_service = history_service
        self.limit = limit
        self.history = defaultdict(deque)

    async def _ensure_loaded(self, chat_id: int):
        if chat_id in self.history or not self.history_service:
            return
        self.history[chat_id].extend(
            await self.history_service.recent_deletable(chat_id, self.limit)
        )

    async def _trim(self, chat_id: int):
        stack = self.history[chat_id]
        while len(stack) > self.limit:
            old_id = stack[0]
            try:
                await self.client.delete_messages(chat_id, old_id)
            except Exception:
                # Keep the record: removing it here would make the cleanup state lie.
                break
            stack.popleft()
            if self.history_service:
                await self.history_service.remove(chat_id, old_id)

    async def add(self, chat_id: int, message_id: int, response_type="temporary"):
        if response_type in self.NON_DELETABLE_TYPES:
            return
        await self._ensure_loaded(chat_id)
        stack = self.history[chat_id]
        if message_id not in stack:
            stack.append(message_id)
        if self.history_service:
            await self.history_service.add(chat_id, message_id, response_type)
        await self._trim(chat_id)
