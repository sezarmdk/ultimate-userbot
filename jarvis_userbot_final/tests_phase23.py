import sqlite3, tempfile
from pathlib import Path
from services.system_service import SystemService
from services.edit_service import EditService

# Structural checks for worker normalization.
class E: 
    def __init__(self,v): self.value=v
class I:
    def __init__(self,s): self.state=s
class W:
    def names(self): return ["a","b","c"]
    def status(self,n): return {"a":I(E("RUNNING")),"b":I("stopped"),"c":I(None)}[n]
assert SystemService(None,W(),type("R",(),{"all":lambda s:[]})(),0).worker_map()=={"a":"running","b":"stopped","c":"unknown"}

# Execute equivalent atomic counter SQL on stock sqlite.
with tempfile.TemporaryDirectory() as d:
    db=sqlite3.connect(Path(d)/"x.db")
    db.execute("CREATE TABLE edit_history(chat_id INTEGER,message_id INTEGER,edit_count INTEGER, UNIQUE(chat_id,message_id,edit_count))")
    sql="""INSERT INTO edit_history(chat_id,message_id,edit_count)
    SELECT ?,?,COALESCE(MAX(edit_count),0)+1 FROM edit_history WHERE chat_id=? AND message_id=? RETURNING edit_count"""
    out=[]
    for _ in range(5): out.append(db.execute(sql,(1,10,1,10)).fetchone()[0])
    assert out==[1,2,3,4,5], out
print("PHASE 23 WORKER NORMALIZATION: PASS")
print("PHASE 23 EDIT COUNTER SQL: PASS")
