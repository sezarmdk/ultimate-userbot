from pathlib import Path
import ast
root=Path('.')
for p in root.rglob('*.py'):
    if '__pycache__' not in p.parts:
        ast.parse(p.read_text(encoding='utf-8'), filename=str(p))
source=Path('main.py').read_text(encoding='utf-8')
expected={"on","off","story","unstory","autoread","autoreadall","unread","taxrir","untaxrir","mute","unmute","log","help","stat","info","ping","calc","autostatus","unstatus","bio","unbio","del","block","unblock"}
for cmd in expected:
    assert f'@self.command("{cmd}"' in source, cmd
assert "exclude_ids=exclude_ids" in source
assert "max(requested * 50, 500)" in Path('services/delete_service.py').read_text(encoding='utf-8')
print('FINAL STATIC AUDIT: PASS')
print(f'PUBLIC COMMANDS: {len(expected)}')
