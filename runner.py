import subprocess
import os
import sys

# Render veb-portini ushlab turish
port = os.environ.get("PORT", "10000")
subprocess.Popen([sys.executable, "-m", "http.server", str(port)])

# 1. Do'stingizning Userboti (Sizdagi barcha buyruqlar bilan)
os.makedirs("inst_friend", exist_ok=True)
os.system("cp main.py inst_friend/ 2>/dev/null")
os.system("cp friend.session inst_friend/ 2>/dev/null")

env_friend = os.environ.copy()
env_friend["API_ID"] = "31917495"
env_friend["API_HASH"] = "bc9a75239f98bc1858683dce6f4a1547"
env_friend["SESSION_NAME"] = "friend"
p1 = subprocess.Popen([sys.executable, "main.py"], cwd="inst_friend", env=env_friend)

# 2. Sizning 2-zaxira hisobingizdagi Auto-Commenter (Tezkor izoh)
p2 = subprocess.Popen([sys.executable, "commenter.py"])

print(">>> Do'stingizning userboti va Auto-Commenter parallel ishga tushirildi! <<<")

p1.wait()
p2.wait()
