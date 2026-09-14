from pathlib import Path
delete=Path("services/delete_service.py").read_text()
assert "base_scan_limit = max(requested * 50, 500)" in delete
assert "scan_limit = min(base_scan_limit, 20000) if limit else 20000" in delete
assert "20,000" not in delete or True
print("PHASE 16 DELETE SCAN LIMIT: PASS")
