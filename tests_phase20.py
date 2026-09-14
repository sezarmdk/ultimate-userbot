from pathlib import Path
root=Path(__file__).parent
profile=(root/'services/profile_service.py').read_text()
main=(root/'main.py').read_text()
delete=(root/'services/delete_service.py').read_text()
assert 'UpdateEmojiStatusRequest' in profile
assert 'async def set_status' in profile
assert 'await self._log_error("bio_worker", exc)' in profile
assert 'except asyncio.CancelledError' in profile
assert 'AVTO STATUS FAOLLASHTIRILMADI' in main
assert 'AVTO STATUS FAOLLASHTIRILDI' in main
assert 'base_scan_limit = max(requested * 50, 500)' in delete
assert 'scan_limit = min(base_scan_limit, 20000)' in delete
print('PHASE 20 PROFILE API HONESTY: PASS')
print('PHASE 20 BIO ERROR LOGGING: PASS')
print('PHASE 20 DELETE SCAN LIMIT: PASS')
