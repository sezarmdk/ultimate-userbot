
class AutoreadService:
    def __init__(self, db):
        self.db=db

    async def initialize(self):
        assert self.db.conn
        await self.db.conn.execute("""CREATE TABLE IF NOT EXISTS feature_state (
            name TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0,
            mode TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        await self.db.conn.commit()

    async def set(self, name, enabled, mode=None):
        assert self.db.conn
        await self.db.conn.execute("""INSERT INTO feature_state(name,enabled,mode,updated_at)
        VALUES(?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(name) DO UPDATE SET enabled=excluded.enabled,mode=excluded.mode,
        updated_at=CURRENT_TIMESTAMP""",(name,int(enabled),mode))
        await self.db.conn.commit()

    async def get(self,name):
        assert self.db.conn
        async with self.db.conn.execute("SELECT enabled,mode FROM feature_state WHERE name=?",(name,)) as c:
            row=await c.fetchone()
        return {"enabled":bool(row[0]),"mode":row[1]} if row else {"enabled":False,"mode":None}
