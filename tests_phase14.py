from pathlib import Path
text=Path("main.py").read_text()
assert "exclude_ids = {progress_id} if progress_id is not None else set()" in text
assert "exclude_ids=exclude_ids" in text
print("PHASE 14 DELETE PROGRESS SAFETY: PASS")
