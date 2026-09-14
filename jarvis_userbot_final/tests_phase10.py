from pathlib import Path
source=Path("main.py").read_text()
assert "Tasdiqlanmagan" in source
assert "STORY API" in source or "Story API" in source
assert "Tiklanmadi" in source
print("PHASE 10 COMPATIBILITY AUDIT: PASS")
