import sqlite3, tempfile
from pathlib import Path
import re
source=Path("database/database.py").read_text()
SCHEMA=re.search(r'SCHEMA = """(.*?)"""', source, re.S).group(1)

with tempfile.TemporaryDirectory() as d:
    path=Path(d)/'test.db'
    conn=sqlite3.connect(path)
    conn.executescript(SCHEMA)
    assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    conn.execute("INSERT INTO command_usage(command,count) VALUES('story',1)")
    conn.execute("UPDATE command_usage SET count=count+1 WHERE command='story'")
    assert conn.execute("SELECT count FROM command_usage WHERE command='story'").fetchone()[0]==2
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'story_targets','story_actions','muted_targets','blocked_targets','edit_history','bio_state','status_state','logs','workers','tasks','response_history'}
    assert required <= tables, required-tables
    conn.close()
print('PHASE 11 DATABASE SCHEMA SMOKE TEST: PASS')
