
from pathlib import Path
import ast, re
from core.registry import CommandRegistry, Command

root=Path(__file__).parent
source=(root/"main.py").read_text()
tree=ast.parse(source)
commands=[]
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr=="command":
        if node.args and isinstance(node.args[0], ast.Constant):
            commands.append(node.args[0].value)

assert len(commands)==len(set(commands)), f"Duplicate decorators: {commands}"
allowed={"on","off","story","unstory","autoread","autoreadall","unread","taxrir","untaxrir","mute","unmute","log","help","stat","info","ping","calc","autostatus","unstatus","bio","unbio","del","block","unblock"}
assert set(commands)==allowed, f"Mismatch: {set(commands)^allowed}"

reg=CommandRegistry()
async def handler(*args): pass
reg.register(Command("x","test","test",handler))
try:
    reg.register(Command("x","test","test",handler))
    raise AssertionError("Duplicate command accepted")
except ValueError:
    pass
reg.validate()

assert '@self.command("target"' not in source
print("PHASE 9 COMMAND AUDIT: PASS")
print("PHASE 9 REGISTRY DUPLICATE TEST: PASS")
print("PHASE 9 PUBLIC COMMAND COUNT:", len(commands))
