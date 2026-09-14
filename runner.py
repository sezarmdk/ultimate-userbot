import subprocess
import os
import sys

# 1-profil uchun papka va fayllar
os.makedirs("inst1", exist_ok=True)
os.system("cp -rn * inst1/ 2>/dev/null")
os.system("cp berdiyorov.session inst1/ 2>/dev/null")

# 2-profil uchun papka va fayllar
os.makedirs("inst2", exist_ok=True)
os.system("cp -rn * inst2/ 2>/dev/null")
os.system("cp friend.session inst2/ 2>/dev/null")

# .env sozlamalarini yaratish
with open("inst1/.env", "w") as f:
    f.write("API_ID=32261789\nAPI_HASH=06254a37741c127fd669909f57e67168\nSESSION_NAME=berdiyorov\nDATABASE_PATH=berdiyorov.db\n")

with open("inst2/.env", "w") as f:
    f.write("API_ID=31917495\nAPI_HASH=bc9a75239f98bc1858683dce6f4a1547\nSESSION_NAME=friend\nDATABASE_PATH=friend.db\n")

# Render veb-portini ushlab turish
port = os.environ.get("PORT", "10000")
subprocess.Popen([sys.executable, "-m", "http.server", str(port)])

# Ikkala botni mustaqil kataloglarda ishga tushirish
p1 = subprocess.Popen([sys.executable, "main.py"], cwd="inst1")
p2 = subprocess.Popen([sys.executable, "main.py"], cwd="inst2")

p1.wait()
p2.wait()
