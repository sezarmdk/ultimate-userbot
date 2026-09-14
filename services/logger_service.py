class LoggerService:
    def __init__(self, db, client):
        self.db=db; self.client=client

    async def initialize(self):
        assert self.db.conn
        # NOTE: database.py's core SCHEMA already defines an UNRELATED table named
        # "logs" (columns: level, source, message) that nothing in this service uses.
        # Because that table is created first with `CREATE TABLE IF NOT EXISTS`,
        # this service's own `CREATE TABLE IF NOT EXISTS logs (...)` used to be a
        # silent no-op and every INSERT INTO logs(kind,message) failed with
        # "table logs has no column named kind". Using a distinct table name avoids
        # the collision entirely instead of trying to ALTER a table owned by another module.
        await self.db.conn.execute("""CREATE TABLE IF NOT EXISTS activity_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
          message TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        await self.db.conn.execute("""CREATE TABLE IF NOT EXISTS log_settings (
          key TEXT PRIMARY KEY, value TEXT NOT NULL
        )""")
        await self.db.conn.commit()

    async def _resolve_channel(self, channel_id):
        """Resolve a log destination from a numeric ID, @username, or invite link.

        Telethon can only turn a *bare* numeric ID (e.g. the "-100..." style ID
        Telegram's UI shows) into an entity if that ID already sits in its local
        session cache -- meaning the account has previously opened a dialog with,
        or received a message from, that chat. A freshly copied channel ID is not
        enough by itself, which is what produced:
            ValueError: Cannot find any entity corresponding to "-100...".
        We first try the direct resolution, then fall back to scanning the
        account's own dialog list (which also warms the cache), before giving up
        with an actionable message.
        """
        raw = str(channel_id).strip()
        candidate = int(raw) if raw.lstrip('-').isdigit() else raw
        try:
            return await self.client.get_entity(candidate)
        except (ValueError, TypeError):
            pass
        if isinstance(candidate, int):
            target_ids = {candidate}
            marked = str(candidate)
            if marked.startswith("-100"):
                target_ids.add(int(marked[4:]))  # unmarked channel id
            async for dialog in self.client.iter_dialogs():
                entity = dialog.entity
                if entity is not None and getattr(entity, "id", None) in target_ids:
                    return entity
        raise ValueError(
            f'Cannot find any entity corresponding to "{channel_id}". '
            "Akkount bu kanal/chatni hali \"ko‘rmagan\" bo‘lishi mumkin. "
            "Avval shu kanalga a'zo bo‘ling (yoki kamida bitta xabar ko‘ring), so‘ng qayta urinib ko‘ring, "
            "yoki ID o‘rniga @username yoki taklif havolasini yuboring."
        )

    async def set_channel(self, channel_id):
        entity=await self._resolve_channel(channel_id)
        test=await self.client.send_message(entity,"🟢 JARVIS Userbot log ulanishi tasdiqlandi.")
        # Store the canonical numeric peer id when Telegram exposes it.
        value=str(getattr(entity, 'id', channel_id))
        await self.db.conn.execute("""INSERT INTO log_settings(key,value) VALUES('channel_id',?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value""",(value,))
        await self.db.conn.commit()
        return entity,test

    async def event(self, kind, message):
        assert self.db.conn
        # Logging must never break the calling command. Earlier builds let an
        # unwrapped INSERT here (originally into a colliding table named "logs")
        # bubble all the way up and abort whatever action triggered it (e.g. a
        # user got muted/blocked locally but the whole .mute/.block command then
        # errored out because of a *logging* failure). Persisting the activity
        # record and notifying the log channel are both best-effort now: any
        # failure is swallowed (and recorded in the generic `errors` table when
        # possible) instead of propagating.
        try:
            await self.db.conn.execute("INSERT INTO activity_logs(kind,message) VALUES(?,?)",(kind,message))
            await self.db.conn.commit()
        except Exception as exc:
            try:
                await self.db.log_error("logger_event", f"{type(exc).__name__}: {str(exc)[:300]}")
            except Exception:
                pass
        try:
            async with self.db.conn.execute("SELECT value FROM log_settings WHERE key='channel_id'") as c:
                row=await c.fetchone()
        except Exception:
            row=None
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
