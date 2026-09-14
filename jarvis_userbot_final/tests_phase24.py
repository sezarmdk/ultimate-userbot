"""
PHASE 24 — SystemService.snapshot() real bug regression.

Real bug found and fixed:
- SystemService.worker_map() called self.workers.names(), but WorkerManager
  never defined that method -> AttributeError every time `.stat`/`.info`
  ran (any command touching SystemService.snapshot()).
- SystemService.snapshot() called self.registry.all(), but CommandRegistry
  only exposes names() -> same crash.

This test exercises the real, undoubled classes end-to-end (no mocks) to
make sure `.stat` can never silently break like this again.
"""
import asyncio

from workers.manager import WorkerManager
from core.registry import CommandRegistry, Command
from services.system_service import SystemService


class _DummyDB:
    """Stands in for Database without needing aiosqlite/network."""
    conn = None


async def _noop():
    await asyncio.sleep(3600)


async def main():
    workers = WorkerManager()
    registry = CommandRegistry()

    async def handler(event, parsed):
        return None

    registry.register(Command(name="ping", description="test", category="system", handler=handler))

    await workers.start("online_worker", _noop)

    system = SystemService(_DummyDB(), workers, registry, started_at=0)
    snapshot = await system.snapshot()

    assert snapshot.commands == 1
    assert "online_worker" in snapshot.workers
    assert snapshot.workers["online_worker"] == "running"
    assert snapshot.database_ok is False  # no real connection, must degrade safely
    assert snapshot.errors == 0

    await workers.stop_all()
    print("PHASE 24 SYSTEM SNAPSHOT CRASH FIX: PASS")


asyncio.run(main())
