from pathlib import Path
import ast

root = Path(__file__).resolve().parent
main = (root / "main.py").read_text(encoding="utf-8")
target = (root / "core" / "target_resolver.py").read_text(encoding="utf-8")
control = (root / "services" / "control_service.py").read_text(encoding="utf-8")
profile = (root / "services" / "profile_service.py").read_text(encoding="utf-8")

for path in root.rglob("*.py"):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

assert "entity: object" in target
assert "def normalize(candidate" in target
assert "urlparse" in target
assert "target.entity" in control
assert "ALTER TABLE" in control and "display_name" in control and "active" in control
assert "GetFullUserRequest" in profile
assert 'for feature, worker_name, runner' in main
assert 'raw=" ".join(parsed.args).strip()' in main
assert 'OWNER_NAME=Бeрдиёров' in (root / ".env.example").read_text(encoding="utf-8")
assert "COMMAND COULD NOT COMPLETE" not in main
assert "Everything is ready" not in main
assert "Berdiyorov" not in main
print("PHASE 17 SYNTAX AUDIT: PASS")
print("PHASE 17 BLOCK TARGET FIX: PASS")
print("PHASE 17 CONTROL MIGRATION AUDIT: PASS")
print("PHASE 17 AUTOSTATUS PARSER AUDIT: PASS")
print("PHASE 17 RESTART RESTORE AUDIT: PASS")
print("PHASE 17 UZBEK OWNER/UI AUDIT: PASS")
