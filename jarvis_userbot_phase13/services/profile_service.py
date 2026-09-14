
import asyncio
import random
from dataclasses import dataclass

@dataclass
class RotationState:
    enabled: bool
    values: list[str]
    mode: str
    interval: int
    previous: str | None
    index: int = 0

class ProfileService:
    def __init__(self, db, client):
        self.db=db
        self.client=client
        self._states={}

    async def initialize(self):
        assert self.db.conn
        await self.db.conn.execute("""CREATE TABLE IF NOT EXISTS profile_state(
            feature TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL,
            values_json TEXT NOT NULL,
            mode TEXT,
            interval INTEGER,
            previous_value TEXT,
            position INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        await self.db.conn.commit()

    async def save(self, feature, state):
        import json
        assert self.db.conn
        await self.db.conn.execute("""INSERT INTO profile_state
        (feature,enabled,values_json,mode,interval,previous_value,position,updated_at)
        VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(feature) DO UPDATE SET enabled=excluded.enabled,
        values_json=excluded.values_json,mode=excluded.mode,interval=excluded.interval,
        previous_value=excluded.previous_value,position=excluded.position,
        updated_at=CURRENT_TIMESTAMP""",
        (feature,int(state.enabled),json.dumps(state.values,ensure_ascii=False),state.mode,
         state.interval,state.previous,state.index))
        await self.db.conn.commit()
        self._states[feature]=state

    async def load(self, feature):
        import json
        if feature in self._states:return self._states[feature]
        assert self.db.conn
        async with self.db.conn.execute("""SELECT enabled,values_json,mode,interval,
        previous_value,position FROM profile_state WHERE feature=?""",(feature,)) as c:
            row=await c.fetchone()
        if not row:return None
        state=RotationState(bool(row[0]),json.loads(row[1]),row[2],row[3],row[4],row[5])
        self._states[feature]=state
        return state

    async def stop(self, feature):
        state=await self.load(feature)
        if not state:return None
        state.enabled=False
        await self.save(feature,state)
        return state

    def next_value(self,state):
        if not state.values:return None
        if state.mode=="random":
            return random.choice(state.values)
        value=state.values[state.index % len(state.values)]
        state.index=(state.index+1)%len(state.values)
        return value

    async def current_bio(self):
        me=await self.client.get_me()
        return getattr(me,"about",None)

    async def set_bio(self,text):
        from telethon.tl.functions.account import UpdateProfileRequest
        await self.client(UpdateProfileRequest(about=text))
        return True

    async def bio_worker(self):
        while True:
            state=await self.load("bio")
            if not state or not state.enabled:return
            value=self.next_value(state)
            try:
                await self.set_bio(value)
                await self.save("bio",state)
            except Exception:
                # State remains enabled; a future explicit restart/reconnect can retry.
                pass
            await asyncio.sleep(max(30,state.interval))

    async def status_worker(self):
        # Telegram emoji-status support differs by MTProto layer/account capability.
        # Never pretend a status was changed until a verified API request succeeds.
        while True:
            state=await self.load("status")
            if not state or not state.enabled:return
            await asyncio.sleep(max(30,state.interval))
