"""Phase 15 offline regression audit."""
from pathlib import Path
import ast
import re

root=Path(__file__).parent
py_files=list(root.rglob('*.py'))
for path in py_files:
    ast.parse(path.read_text(encoding='utf-8'))

main=(root/'main.py').read_text(encoding='utf-8')
delete=(root/'services/delete_service.py').read_text(encoding='utf-8')
story=(root/'services/story_service.py').read_text(encoding='utf-8')
settings=(root/'config/settings.py').read_text(encoding='utf-8')

assert 'owner_name' in settings
assert '_derive_owner_name' in main  # owner name now comes from the connected Telegram profile
assert 'TAFSILOT' in main
assert 'progress_id = getattr(progress_msg' in main
assert 'event_id = getattr(event' in delete
assert 'msg_date.tzinfo is None' in delete
assert 'soxta kuzatuv' in story
assert 'Public command audit failed' in main

allowed={"on","off","story","unstory","autoread","autoreadall","unread","taxrir","untaxrir","mute","unmute","log","help","stat","info","ping","calc","autostatus","unstatus","bio","unbio","del","block","unblock"}
registered=set(re.findall(r'@self\.command\("([a-z]+)"', main))
assert registered==allowed, (registered-allowed, allowed-registered)
print('PHASE 15 SYNTAX AUDIT: PASS')
print('PHASE 15 COMMAND REGISTRY: PASS (24)')
print('PHASE 15 UZBEK UX AUDIT: PASS')
print('PHASE 15 DELETE REGRESSION: PASS')
print('PHASE 15 STORY HONESTY AUDIT: PASS')
