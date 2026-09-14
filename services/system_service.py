
import os, time, platform
from dataclasses import dataclass

@dataclass
class SystemSnapshot:
    uptime: float
    database_ok: bool
    workers: dict
    commands: int
    errors: int

class SystemService:
    def __init__(self, db, workers, registry, started_at):
        self.db=db
        self.workers=workers
        self.registry=registry
        self.started_at=started_at

    async def database_ok(self):
        try:
            assert self.db.conn
            async with self.db.conn.execute("PRAGMA quick_check") as c:
                row=await c.fetchone()
            return bool(row and row[0]=="ok")
        except Exception:
            return False

    async def error_count(self):
        try:
            assert self.db.conn
            async with self.db.conn.execute("SELECT COUNT(*) FROM errors") as c:
                return int((await c.fetchone())[0])
        except Exception:
            return 0

    async def command_count(self):
        try:
            assert self.db.conn
            async with self.db.conn.execute("SELECT COUNT(*) FROM command_usage") as c:
                return int((await c.fetchone())[0])
        except Exception:
            return 0

    def worker_map(self):
        result={}
        for name in self.workers.names():
            item=self.workers.status(name)
            result[name]=getattr(getattr(item,"state",None),"value","unknown")
        return result

    async def snapshot(self):
        return SystemSnapshot(
            uptime=time.monotonic()-self.started_at,
            database_ok=await self.database_ok(),
            workers=self.worker_map(),
            commands=len(self.registry.all()),
            errors=await self.error_count(),
        )

    @staticmethod
    def environment():
        return {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pid": os.getpid(),
        }
