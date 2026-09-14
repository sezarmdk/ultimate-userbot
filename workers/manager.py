import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

class WorkerState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    FAILED = "failed"

@dataclass
class WorkerInfo:
    name: str
    state: WorkerState = WorkerState.STOPPED
    started_at: datetime | None = None
    task: asyncio.Task | None = None
    error: str | None = None

class WorkerManager:
    def __init__(self):
        self._workers: dict[str, WorkerInfo] = {}
        self._lock = asyncio.Lock()

    async def start(self, name: str, factory):
        async with self._lock:
            info = self._workers.get(name)
            if info and info.state == WorkerState.RUNNING and info.task and not info.task.done():
                return info, False

            info = WorkerInfo(name=name, state=WorkerState.RUNNING,
                              started_at=datetime.now(timezone.utc))
            async def runner():
                try:
                    await factory()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    info.state = WorkerState.FAILED
                    info.error = f"{type(exc).__name__}: {exc}"
                    raise
                finally:
                    if info.state == WorkerState.RUNNING:
                        info.state = WorkerState.STOPPED

            info.task = asyncio.create_task(runner(), name=f"worker:{name}")
            self._workers[name] = info
            return info, True

    async def stop(self, name: str) -> bool:
        async with self._lock:
            info = self._workers.get(name)
            if not info or not info.task or info.task.done():
                return False
            info.task.cancel()
            try:
                await info.task
            except asyncio.CancelledError:
                pass
            info.state = WorkerState.STOPPED
            return True

    def status(self, name: str) -> WorkerInfo | None:
        return self._workers.get(name)

    def all_status(self):
        return list(self._workers.values())

    async def stop_all(self):
        for name in list(self._workers):
            await self.stop(name)
