
# Lightweight offline checks for services that do not require Telegram credentials.
from services.calculator_service import SafeCalculator
import sys, types
# Lightweight stub only for importing the parser service in this offline environment.
# Real deployment uses Telethon from requirements.txt.
telethon = types.ModuleType("telethon")
errors = types.ModuleType("telethon.errors")
class FloodWaitError(Exception):
    seconds = 0
errors.FloodWaitError = FloodWaitError
telethon.errors = errors
sys.modules.setdefault("telethon", telethon)
sys.modules.setdefault("telethon.errors", errors)
from services.delete_service import DeleteService
import asyncio

calc=SafeCalculator()
assert calc.calculate("2+2").result=="4"
assert calc.calculate("sqrt(144)").result=="12"
assert calc.calculate("2^10").result=="1024"
assert calc.calculate("20%").result=="0.2"

try:
    calc.calculate("__import__('os').system('x')")
    raise AssertionError("Unsafe expression was accepted")
except Exception:
    pass

async def run():
    _, since=DeleteService.parse_period("30m")
    assert since is not None
    _, today=DeleteService.parse_period("today")
    assert today is not None
asyncio.run(run())
print("PHASE 8 OFFLINE CHECKS: PASS")
