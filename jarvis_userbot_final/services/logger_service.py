class LoggerService:
    def __init__(self, db, client):
        self.db=db; self.client=client

    async def initialize(self):
        assert self.db.conn
        await self.db.conn.execute("""CREATE TABLE IF NOT EXISTS logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
          message TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        await self.db.conn.execute("""CREATE TABLE IF NOT EXISTS log_settings (
          key TEXT PRIMARY KEY, value TEXT NOT NULL
        )""")
        await self.db.conn.commit()

    async def set_channel(self, channel_id):
        entity=await self.client.get_entity(channel_id)
        test=await self.client.send_message(entity,"🟢 JARVIS Userbot log ulanishi tasdiqlandi.")
        # Store the canonical numeric peer id when Telegram exposes it.
        value=str(getattr(entity, 'id', channel_id))
        await self.db.conn.execute("""INSERT INTO log_settings(key,value) VALUES('channel_id',?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value""",(value,))
        await self.db.conn.commit()
        return entity,test

    async def event(self, kind, message):
        assert self.db.conn
        await self.db.conn.execute("INSERT INTO logs(kind,message) VALUES(?,?)",(kind,message))
        await self.db.conn.commit()
        async with self.db.conn.execute("SELECT value FROM log_settings WHERE key='channel_id'") as c:
            row=await c.fetchone()
        if row:
            try:
                target=int(row[0]) if str(row[0]).lstrip('-').isdigit() else row[0]
                await self.client.send_message(target,f"📜 **{kind}**\n\n{message}",parse_mode="md")
            except Exception as exc:
                # Logging must never break the main user action.
                try:
                    await self.db.log_error("logger_delivery", f"{type(exc).__name__}: {str(exc)[:300]}")
                except Exception:
                    pass

    async def error(self, kind, exc):
        await self.event(f"XATO: {kind}", f"{type(exc).__name__}: {str(exc)[:500]}")
