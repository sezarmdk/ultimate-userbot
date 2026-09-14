
import asyncio
import random
import re
from dataclasses import dataclass


class ProfilePackError(Exception):
    """Raised when an emoji-pack link/name can't be resolved into emoji IDs."""


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

    def extract_custom_emoji_ids(self, message):
        """Pull premium/custom emoji document IDs straight out of a message's
        entities, so the user can paste the emoji itself instead of looking up
        its numeric ID (e.g. `.autostatus` followed by a pasted premium emoji)."""
        from telethon.tl.types import MessageEntityCustomEmoji
        entities = getattr(message, "entities", None) or []
        ids = [str(e.document_id) for e in entities if isinstance(e, MessageEntityCustomEmoji)]
        return list(dict.fromkeys(ids))

    async def resolve_pack_emojis(self, pack_ref):
        """Resolve a custom-emoji pack -- given as a bare short name or a full
        t.me/addemoji/<name> (or addstickers) link -- into every custom-emoji
        document ID it contains, so `.autostatus <pack link>` can rotate through
        the whole pack instead of requiring individual numeric IDs."""
        from telethon.tl.functions.messages import GetStickerSetRequest
        from telethon.tl.types import InputStickerSetShortName

        ref = (pack_ref or "").strip()
        match = re.search(r'(?:addemoji|addstickers)/([A-Za-z0-9_]+)', ref)
        short_name = match.group(1) if match else ref.lstrip('@').strip()
        short_name = short_name.split('?')[0].strip('/')
        if not short_name:
            raise ProfilePackError("Emoji pack nomi yoki havolasi aniqlanmadi.")
        try:
            result = await self.client(GetStickerSetRequest(
                stickerset=InputStickerSetShortName(short_name=short_name), hash=0))
        except Exception as exc:
            raise ProfilePackError(
                f"Pack topilmadi yoki yuklab bo‘lmadi (`{short_name}`): {type(exc).__name__}: {exc}"
            ) from exc
        documents = getattr(result, "documents", None) or []
        ids = [str(doc.id) for doc in documents if getattr(doc, "id", None) is not None]
        if not ids:
            raise ProfilePackError(f"`{short_name}` packida hech qanday emoji topilmadi.")
        return list(dict.fromkeys(ids))

    async def current_bio(self):
        # get_me() odatda "about" maydonini bermaydi; to‘liq foydalanuvchi ma'lumotini so‘raymiz.
        from telethon.tl.functions.users import GetFullUserRequest
        me = await self.client.get_me()
        full = await self.client(GetFullUserRequest(me))
        return getattr(getattr(full, "full_user", None), "about", None)

    async def set_bio(self,text):
        from telethon.tl.functions.account import UpdateProfileRequest
        await self.client(UpdateProfileRequest(about=text))
        return True

    async def _log_error(self, source, exc):
        try:
            await self.db.log_error(source, exc)
        except Exception:
            # Logging must never kill a profile worker.
            return

    async def set_status(self, emoji_id):
        """Attempt the current Telethon MTProto path and return only confirmed success."""
        try:
            from telethon.tl.functions.account import UpdateEmojiStatusRequest
            from telethon.tl.types import EmojiStatus
        except ImportError as exc:
            return False, f"Emoji status API mavjud emas: {type(exc).__name__}"
        try:
            await self.client(UpdateEmojiStatusRequest(emoji_status=EmojiStatus(document_id=int(emoji_id))))
            return True, None
        except Exception as exc:
            await self._log_error("status_worker", exc)
            return False, f"{type(exc).__name__}: {exc}"

    async def bio_worker(self):
        while True:
            state=await self.load("bio")
            if not state or not state.enabled:return
            value=self.next_value(state)
            try:
                await self.set_bio(value)
                await self.save("bio",state)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._log_error("bio_worker", exc)
                # Keep state enabled, but persist the advanced sequence position.
                await self.save("bio",state)
            await asyncio.sleep(max(30,state.interval))

    async def status_worker(self):
        while True:
            state=await self.load("status")
            if not state or not state.enabled:return
            value=self.next_value(state)
            ok, error = await self.set_status(value)
            if ok:
                await self.save("status",state)
            else:
                # Stop repeated blind retries when this MTProto layer/account cannot support it.
                state.enabled=False
                await self.save("status",state)
                return
            await asyncio.sleep(max(30,state.interval))
