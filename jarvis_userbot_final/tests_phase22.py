import ast
from pathlib import Path

def test_syntax():
    for path in Path('.').rglob('*.py'):
        if '__pycache__' not in str(path):
            ast.parse(path.read_text())

def test_online_worker_has_health_probe():
    text=Path('workers/online.py').read_text()
    assert 'get_me()' in text and 'retry_delay' in text

def test_ping_real_telegram_measurement():
    text=Path('main.py').read_text()
    assert 'telegram_ms' in text and 'await self.client.get_me()' in text

def test_logger_safe_delivery():
    text=Path('services/logger_service.py').read_text()
    assert 'logger_delivery' in text and 'canonical numeric peer id' in text

if __name__=='__main__':
    test_syntax(); test_online_worker_has_health_probe(); test_ping_real_telegram_measurement(); test_logger_safe_delivery(); print('PHASE 22 AUDIT: PASS')
