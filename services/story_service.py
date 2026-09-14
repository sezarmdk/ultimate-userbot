
from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio
from telethon import errors

@dataclass(frozen=True)
class StoryTarget:
    user_id: int
    username: str | None
    display_name: str
    reaction: str | None
    active: bool

class StoryService:
    def __init__(self, db, client):
        self.db = db
        self.client = client
        self._lock = asyncio.Lock()

    async def initialize(self):
        assert self.db.conn
        await self.db.conn.executescript("""
        CREATE TABLE IF NOT EXISTS story_targets (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            display_name TEXT,
            reaction TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_checked_at TEXT,
            last_story_id INTEGER,
            stories_processed INTEGER NOT NULL DEFAULT 0,
            reactions_successful INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS story_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            story_id INTEGER,
            reaction TEXT,
            status TEXT NOT NULL,
            error TEXT,
            timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, story_id, reaction)
        );

        CREATE INDEX IF NOT EXISTS idx_story_actions_user_story
        ON story_actions(user_id, story_id);
        """)
        await self.db.conn.commit()

    async def add_target(self, target, reaction=None):
        assert self.db.conn
        async with self._lock:
            async with self.db.conn.execute(
                "SELECT user_id FROM story_targets WHERE user_id=?", (target.user_id,)
            ) as cur:
                exists = await cur.fetchone()

            if exists:
                await self.db.conn.execute(
                    """UPDATE story_targets SET username=?, display_name=?, reaction=?,
                    active=1 WHERE user_id=?""",
                    (target.username, target.display_name, reaction, target.user_id)
                )
                created = False
            else:
                await self.db.conn.execute(
                    """INSERT INTO story_targets
                    (user_id, username, display_name, reaction, active)
                    VALUES (?, ?, ?, ?, 1)""",
                    (target.user_id, target.username, target.display_name, reaction)
                )
                created = True
            await self.db.conn.commit()
            return created

    async def remove_target(self, user_id):
        assert self.db.conn
        result = await self.db.conn.execute(
            "UPDATE story_targets SET active=0 WHERE user_id=? AND active=1", (user_id,)
        )
        await self.db.conn.commit()
        return result.rowcount > 0

    async def get_target(self, user_id):
        assert self.db.conn
        async with self.db.conn.execute(
            """SELECT user_id, username, display_name, reaction, active
            FROM story_targets WHERE user_id=?""", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return StoryTarget(*row) if row else None

    async def list_targets(self):
        assert self.db.conn
        async with self.db.conn.execute(
            """SELECT user_id, username, display_name, reaction, active
            FROM story_targets WHERE active=1 ORDER BY added_at DESC"""
        ) as cur:
            rows = await cur.fetchall()
        return [StoryTarget(*row) for row in rows]

    async def stats(self):
        assert self.db.conn
        async with self.db.conn.execute(
            """SELECT COUNT(*), COALESCE(SUM(reactions_successful),0),
            COALESCE(SUM(errors),0) FROM story_targets WHERE active=1"""
        ) as cur:
            active, reactions, errors_count = await cur.fetchone()
        return {"active": active, "reactions": reactions, "errors": errors_count}

    async def mark_checked(self, user_id):
        assert self.db.conn
        await self.db.conn.execute(
            "UPDATE story_targets SET last_checked_at=? WHERE user_id=?",
            (datetime.now(timezone.utc).isoformat(), user_id)
        )
        await self.db.conn.commit()

    async def already_processed(self, user_id, story_id, reaction):
        assert self.db.conn
        async with self.db.conn.execute(
            """SELECT 1 FROM story_actions
            WHERE user_id=? AND story_id=? AND reaction IS ?""",
            (user_id, story_id, reaction)
        ) as cur:
            return await cur.fetchone() is not None

    async def record_action(self, user_id, story_id, reaction, status, error=None):
        assert self.db.conn
        try:
            await self.db.conn.execute(
                """INSERT OR IGNORE INTO story_actions
                (user_id, story_id, reaction, status, error)
                VALUES (?, ?, ?, ?, ?)""",
                (user_id, story_id, reaction, status, error)
            )
            if status == "success":
                await self.db.conn.execute(
                    """UPDATE story_targets SET stories_processed=stories_processed+1,
                    reactions_successful=reactions_successful+1,
                    last_story_id=? WHERE user_id=?""",
                    (story_id, user_id)
                )
            elif status == "error":
                await self.db.conn.execute(
                    "UPDATE story_targets SET errors=errors+1 WHERE user_id=?",
                    (user_id,)
                )
            await self.db.conn.commit()
        except Exception:
            await self.db.conn.rollback()
            raise

    async def check_target(self, target):
        """
        Compatibility-first check.
        Telethon exposes Story TL types, but story feed/reaction availability can
        differ by Telegram layer and account capability. This method never claims
        a reaction unless an actual API call is implemented and confirmed.
        """
        await self.mark_checked(target.user_id)
        return {
            "supported": False,
            "checked": True,
            "stories_found": None,
            "reacted": 0,
            "reason": (
                "Story fetching/reaction is not enabled in this build until the "
                "installed Telethon layer exposes a verified compatible API path."
            ),
        }
