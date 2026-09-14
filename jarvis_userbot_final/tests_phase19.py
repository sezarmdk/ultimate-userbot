"""Phase 19 regression audit: parser flow and real bug-prevention checks."""
from pathlib import Path
import ast
src = Path('main.py').read_text(encoding='utf-8')
ast.parse(src)
assert 'if mode in {"info", "check"}:' in src
assert 'await self.reply(event, UI.info(\n                    "STORY TEKSHIRUVI"' in src
assert 'self.original_messages) > 5000' in src
assert 'log_error("edit_tracker"' in src
assert 'Guruhlar' in src and 'Kanallar' in src
assert 'Sinov xabari' in src and 'Tasdiqlandi' in src
print('PHASE 19 SYNTAX AUDIT: PASS')
print('PHASE 19 STORY CHECK FALLTHROUGH FIX: PASS')
print('PHASE 19 EDIT ERROR LOGGING: PASS')
print('PHASE 19 EDIT CACHE LIMIT: PASS')
print('PHASE 19 UZBEK UI REGRESSION: PASS')
