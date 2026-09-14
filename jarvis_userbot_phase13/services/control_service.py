
class ControlService:
    def __init__(self, db, client):
        self.db=db; self.client=client

    async def initialize(self):
        assert self.db.conn
        await self.db.conn.executescript("""
        CREATE TABLE IF NOT EXISTS muted_targets(
          user_id INTEGER PRIMARY KEY, username TEXT, display_name TEXT,
          active INTEGER NOT NULL DEFAULT 1, added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS blocked_targets(
          user_id INTEGER PRIMARY KEY, username TEXT, display_name TEXT,
          active INTEGER NOT NULL DEFAULT 1, added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        await self.db.conn.commit()

    async def _set(self, table, target, active):
        assert self.db.conn
        if active:
            await self.db.conn.execute(
                f"""INSERT INTO {table}(user_id,username,display_name,active)
                VALUES(?,?,?,1)
                ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
                display_name=excluded.display_name,active=1""",
                (target.user_id,target.username,target.display_name))
        else:
            result=await self.db.conn.execute(
                f"UPDATE {table} SET active=0 WHERE user_id=? AND active=1",(target.user_id,))
            if result.rowcount < 1:
                await self.db.conn.commit()
                return False
        await self.db.conn.commit()
        return True

    async def mute(self,target):
        # Telegram user accounts don't expose a universal server-side "mute user"
        # primitive. Persisting a local mute policy is honest and can be enforced
        # by notification/dialog handling without claiming account-level blocking.
        return await self._set("muted_targets",target,True)

    async def unmute(self,target): return await self._set("muted_targets",target,False)

    async def block(self,target):
        from telethon.tl.functions.contacts import BlockRequest
        await self.client(BlockRequest(target.entity))
        return await self._set("blocked_targets",target,True)

    async def unblock(self,target):
        from telethon.tl.functions.contacts import UnblockRequest
        await self.client(UnblockRequest(target.entity))
        return await self._set("blocked_targets",target,False)

    async def _get(self,table,user_id):
        assert self.db.conn
        async with self.db.conn.execute(
            f"SELECT user_id,username,display_name,active FROM {table} WHERE user_id=?",(user_id,)) as c:
            row=await c.fetchone()
        return row

    async def muted(self,user_id): return await self._get("muted_targets",user_id)
    async def blocked(self,user_id): return await self._get("blocked_targets",user_id)

    async def _list(self,table):
        assert self.db.conn
        async with self.db.conn.execute(
            f"SELECT user_id,username,display_name FROM {table} WHERE active=1 ORDER BY added_at DESC") as c:
            return await c.fetchall()

    async def mute_list(self): return await self._list("muted_targets")
    async def block_list(self): return await self._list("blocked_targets")

    async def counts(self):
        assert self.db.conn
        result={}
        for key,table in [("muted","muted_targets"),("blocked","blocked_targets")]:
            async with self.db.conn.execute(f"SELECT COUNT(*) FROM {table} WHERE active=1") as c:
                result[key]=(await c.fetchone())[0]
        return result
