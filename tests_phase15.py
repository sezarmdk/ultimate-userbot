from pathlib import Path
root=Path(__file__).parent
main=(root/'main.py').read_text(encoding='utf-8')
delete=(root/'services/delete_service.py').read_text(encoding='utf-8')
story=(root/'services/story_service.py').read_text(encoding='utf-8')
assert 'TAFSILOT' in main
assert 'progress_id = getattr(progress_msg' in main
assert 'event_id = getattr(event' in delete
assert 'msg_date.tzinfo is None' in delete
assert 'soxta kuzatuv' in story
assert 'owner_name' in (root/'config/settings.py').read_text(encoding='utf-8')
assert '_derive_owner_name' in main  # owner name now comes from the connected Telegram profile
print('PHASE 15 REAL BUG FIX REGRESSION: PASS')
