import asyncio, ast, tempfile
from pathlib import Path
from database.database import Database
from core.registry import CommandRegistry, Command

async def main():
    path=Path(tempfile.gettempdir())/"jarvis_phase12_test.sqlite"
    if path.exists(): path.unlink()
    db=Database(path)
    await db.connect()
    assert await db.quick_check()
    await db.increment_command("help")
    await db.increment_command("help")
    assert await db.integrity_check()=="ok"
    await db.close()
    path.unlink(missing_ok=True)

asyncio.run(main())
reg=CommandRegistry()
async def h(*a): pass
reg.register(Command("x","d","c",h))
try:
    reg.register(Command("x","d","c",h)); raise AssertionError
except ValueError: pass
source=Path("main.py").read_text(); ast.parse(source)
assert "Not measured — no fake network latency" in source
assert "2 / Core Intelligence" not in source
print("PHASE 12 DATABASE RUNTIME TEST: PASS")
print("PHASE 12 PRODUCTION SOURCE AUDIT: PASS")
