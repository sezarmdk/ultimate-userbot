class ResponseHistoryService:
    def __init__(self, db):
        self.db = db

    async def add(self, chat_id: int, message_id: int, response_type: str,
                  persistent: bool = False, deletable: bool = True):
        assert self.db.conn
        await self.db.conn.execute(
            """INSERT OR IGNORE INTO response_history
            (chat_id, message_id, response_type, persistent, deletable)
            VALUES (?, ?, ?, ?, ?)""",
            (chat_id, message_id, response_type, int(persistent), int(deletable)),
        )
        await self.db.conn.commit()

    async def oldest_deletable(self, chat_id: int):
        assert self.db.conn
        async with self.db.conn.execute(
            """SELECT message_id FROM response_history
            WHERE chat_id=? AND deletable=1 AND persistent=0
            ORDER BY created_at ASC, message_id ASC LIMIT 1""",
            (chat_id,),
        ) as cur:
            return await cur.fetchone()

    async def remove(self, chat_id: int, message_id: int):
        assert self.db.conn
        await self.db.conn.execute(
            "DELETE FROM response_history WHERE chat_id=? AND message_id=?",
            (chat_id, message_id),
        )
        await self.db.conn.commit()

    async def recent_deletable(self, chat_id: int, limit: int = 2):
        assert self.db.conn
        async with self.db.conn.execute(
            """SELECT message_id FROM response_history
            WHERE chat_id=? AND deletable=1 AND persistent=0
            ORDER BY created_at DESC, message_id DESC LIMIT ?""",
            (chat_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [int(row[0]) for row in reversed(rows)]
