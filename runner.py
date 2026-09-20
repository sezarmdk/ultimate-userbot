import subprocess
import os
import sys

# 1-instansiya: Nurbek
os.makedirs("inst1", exist_ok=True)
os.system("cp main.py inst1/ 2>/dev/null")
os.system("cp berdiyorov.session inst1/ 2>/dev/null")

env1 = os.environ.copy()
env1["API_ID"] = "32261789"
env1["API_HASH"] = "06254a37741c127fd669909f57e67168"
env1["SESSION_NAME"] = "berdiyorov"

# 2-instansiya: Do'stingiz
os.makedirs("inst2", exist_ok=True)
os.system("cp main.py inst2/ 2>/dev/null")
os.system("cp friend.session inst2/ 2>/dev/null")

env2 = os.environ.copy()
env2["API_ID"] = "31917495"
env2["API_HASH"] = "bc9a75239f98bc1858683dce6f4a1547"
env2["SESSION_NAME"] = "friend"

# Render veb-portini ushlab turish
port = os.environ.get("PORT", "10000")
subprocess.Popen([sys.executable, "-m", "http.server", str(port)])

# Ikkala botni alohida jarayon va sozlamalar bilan ishga tushirish
p1 = subprocess.Popen([sys.executable, "main.py"], cwd="inst1", env=env1)
p2 = subprocess.Popen([sys.executable, "main.py"], cwd="inst2", env=env2)

p1.wait()
p2.wait()
