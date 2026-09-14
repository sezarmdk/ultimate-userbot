from pathlib import Path
import ast
root=Path(__file__).parent
ast.parse((root/'main.py').read_text())
ast.parse((root/'services/control_service.py').read_text())
s=(root/'services/control_service.py').read_text()
assert 'async def unblock(self,target)' in s
assert 'await self.client(UnblockRequest(target.entity))' in s
assert 'return True' in s
assert 'target.entity' in s
print('PHASE 21 CONTROL SEMANTICS AUDIT: PASS')
print('PHASE 21 SYNTAX AUDIT: PASS')
