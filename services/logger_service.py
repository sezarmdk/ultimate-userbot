
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
        test=await self.client.send_message(entity,"🟢 Jarvis Userbot log connection verified.")
        await self.db.conn.execute("""INSERT INTO log_settings(key,value) VALUES('channel_id',?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value""",(str(channel_id),))
        await self.db.conn.commit()
        return entity,test

    async def event(self, kind, message):
        assert self.db.conn
        await self.db.conn.execute("INSERT INTO logs(kind,message) VALUES(?,?)",(kind,message))
        await self.db.conn.commit()
        async with self.db.conn.execute("SELECT value FROM log_settings WHERE key='channel_id'") as c:
            row=await c.fetchone()
        if row:
            try: await self.client.send_message(int(row[0]),f"📜 **{kind}**\n\n{message}",parse_mode="md")
            except Exception: pass
