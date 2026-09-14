import aiosqlite
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS response_history (
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    response_type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    persistent INTEGER NOT NULL DEFAULT 0,
    deletable INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_response_history_chat_created
ON response_history(chat_id, created_at);

CREATE TABLE IF NOT EXISTS statistics (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS command_usage (
    command TEXT PRIMARY KEY,
    count INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS story_targets (user_id INTEGER PRIMARY KEY, username TEXT, reaction TEXT, enabled INTEGER NOT NULL DEFAULT 1, added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_checked_at TEXT);
CREATE TABLE IF NOT EXISTS story_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, story_id INTEGER NOT NULL, reaction TEXT, status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, story_id, reaction));
CREATE TABLE IF NOT EXISTS muted_targets (user_id INTEGER PRIMARY KEY, username TEXT, added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS blocked_targets (user_id INTEGER PRIMARY KEY, username TEXT, added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS edit_history (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, message_id INTEGER, user_id INTEGER, original_text TEXT, new_text TEXT, original_time TEXT, edit_time TEXT, edit_count INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS bio_state (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0, state_json TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS status_state (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0, state_json TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, level TEXT NOT NULL, source TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS workers (name TEXT PRIMARY KEY, state TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, state TEXT NOT NULL, payload TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_story_actions_user_story ON story_actions(user_id, story_id);
CREATE INDEX IF NOT EXISTS idx_edit_history_chat_message ON edit_history(chat_id, message_id);
"""

class Database:
    def __init__(self, path: Path):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def integrity_check(self) -> str:
        assert self.conn
        async with self.conn.execute("PRAGMA integrity_check") as cursor:
            row = await cursor.fetchone()
            return row[0]

    async def increment_command(self, command: str) -> None:
        assert self.conn
        await self.conn.execute(
            """INSERT INTO command_usage(command, count, last_used_at)
               VALUES (?, 1, CURRENT_TIMESTAMP)
               ON CONFLICT(command) DO UPDATE SET
               count=count+1, last_used_at=CURRENT_TIMESTAMP""",
            (command,),
        )
        await self.conn.commit()

    async def log_error(self, source: str, exc: Exception | str) -> None:
        assert self.conn
        await self.conn.execute("INSERT INTO errors(source,error_type,message) VALUES(?,?,?)", (source, type(exc).__name__ if isinstance(exc, Exception) else "Error", str(exc)))
        await self.conn.commit()

    async def quick_check(self) -> bool:
        assert self.conn
        async with self.conn.execute("PRAGMA quick_check") as cursor:
            row = await cursor.fetchone()
            return bool(row and row[0] == "ok")

    async def close(self) -> None:
        if self.conn:
            await self.conn.commit()
            await self.conn.close()
            self.conn = None
