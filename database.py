import aiosqlite
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS response_history (
    chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL, response_type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, persistent INTEGER NOT NULL DEFAULT 0,
    deletable INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(chat_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_response_history_chat_created ON response_history(chat_id, created_at);
CREATE TABLE IF NOT EXISTS statistics (key TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS command_usage (command TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0, last_used_at TEXT);
CREATE TABLE IF NOT EXISTS errors (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, error_type TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

-- Canonical Story schema. Older databases are migrated in connect().
CREATE TABLE IF NOT EXISTS story_targets (
    user_id INTEGER PRIMARY KEY, username TEXT, display_name TEXT, reaction TEXT,
    active INTEGER NOT NULL DEFAULT 1, added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TEXT, last_story_id INTEGER, stories_processed INTEGER NOT NULL DEFAULT 0,
    reactions_successful INTEGER NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS story_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, story_id INTEGER,
    reaction TEXT, status TEXT NOT NULL, error TEXT,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, story_id, reaction)
);
CREATE INDEX IF NOT EXISTS idx_story_actions_user_story ON story_actions(user_id, story_id);
CREATE TABLE IF NOT EXISTS muted_targets (user_id INTEGER PRIMARY KEY, username TEXT, added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS blocked_targets (user_id INTEGER PRIMARY KEY, username TEXT, added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS edit_history (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, message_id INTEGER, user_id INTEGER, original_text TEXT, new_text TEXT, original_time TEXT, edit_time TEXT, edit_count INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS idx_edit_history_chat_message ON edit_history(chat_id, message_id);
CREATE TABLE IF NOT EXISTS bio_state (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0, state_json TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS status_state (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0, state_json TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, level TEXT NOT NULL, source TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS workers (name TEXT PRIMARY KEY, state TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, state TEXT NOT NULL, payload TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""

class Database:
    def __init__(self, path: Path):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def _columns(self, table: str) -> set[str]:
        assert self.conn
        async with self.conn.execute(f"PRAGMA table_info({table})") as cursor:
            return {str(row[1]) for row in await cursor.fetchall()}

    async def _ensure_column(self, table: str, name: str, definition: str) -> None:
        assert self.conn
        if name not in await self._columns(table):
            await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    async def _migrate_story_schema(self) -> None:
        """Upgrade Phase 1-13 story tables without dropping user data."""
        assert self.conn
        cols = await self._columns("story_targets")
        additions = {
            "display_name": "TEXT",
            "active": "INTEGER NOT NULL DEFAULT 1",
            "last_story_id": "INTEGER",
            "stories_processed": "INTEGER NOT NULL DEFAULT 0",
            "reactions_successful": "INTEGER NOT NULL DEFAULT 0",
            "errors": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in additions.items():
            if name not in cols:
                await self._ensure_column("story_targets", name, definition)
        cols = await self._columns("story_targets")
        if "enabled" in cols:
            await self.conn.execute("UPDATE story_targets SET active=enabled WHERE enabled IS NOT NULL")
        await self.conn.execute("UPDATE story_targets SET display_name=COALESCE(NULLIF(display_name,''), NULLIF(username,''), CAST(user_id AS TEXT))")

        action_cols = await self._columns("story_actions")
        if "timestamp" not in action_cols:
            await self._ensure_column("story_actions", "timestamp", "TEXT")
            if "created_at" in action_cols:
                await self.conn.execute("UPDATE story_actions SET timestamp=created_at WHERE timestamp IS NULL")

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True) if self.path.parent != Path('.') else None
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.executescript(SCHEMA)
        await self._migrate_story_schema()
        await self.conn.commit()

    async def integrity_check(self) -> str:
        assert self.conn
        async with self.conn.execute("PRAGMA integrity_check") as cursor:
            row = await cursor.fetchone()
            return row[0]

    async def increment_command(self, command: str) -> None:
        assert self.conn
        await self.conn.execute("""INSERT INTO command_usage(command, count, last_used_at) VALUES (?,1,CURRENT_TIMESTAMP)
        ON CONFLICT(command) DO UPDATE SET count=count+1,last_used_at=CURRENT_TIMESTAMP""", (command,))
        await self.conn.commit()

    async def log_error(self, source: str, exc: Exception | str) -> None:
        assert self.conn
        error_type = type(exc).__name__ if isinstance(exc, Exception) else "Error"
        await self.conn.execute("INSERT INTO errors(source,error_type,message) VALUES(?,?,?)", (source,error_type,str(exc)))
        await self.conn.commit()

    async def quick_check(self) -> bool:
        assert self.conn
        async with self.conn.execute("PRAGMA quick_check") as cursor:
            row = await cursor.fetchone()
            return bool(row and row[0] == "ok")

    async def close(self) -> None:
        if self.conn:
            await self.conn.commit(); await self.conn.close(); self.conn=None
