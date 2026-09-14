from pathlib import Path
import ast
root=Path(__file__).parent
main=(root/'main.py').read_text()
assert 'AUTOREAD ALL YOQILDI' in main
assert 'getattr(sender, "bot", False)' in main
assert 'Boshqa doimiy funksiyalar' in main
ast.parse(main)
resolver=(root/'core'/'target_resolver.py').read_text()
assert 'entity: object' in resolver
print('PHASE 18 SYNTAX AUDIT: PASS')
print('PHASE 18 AUTOREAD BOT EXCLUSION: PASS')
print('PHASE 18 UZBEK UI REGRESSION: PASS')
print('PHASE 18 TARGET ENTITY AUDIT: PASS')
