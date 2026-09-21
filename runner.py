import subprocess
import os
import sys

port = os.environ.get("PORT", "10000")
subprocess.Popen([sys.executable, "-m", "http.server", str(port)])

# 1. SIZNING ASOSIY PROFILINGIZ (Asosiy bot: .ping, .info, .on, .read, .astatus)
os.makedirs("inst_main", exist_ok=True)
os.system("cp main.py inst_main/ 2>/dev/null")
os.system("cp berdiyorov.session inst_main/ 2>/dev/null")
env_main = os.environ.copy()
env_main["API_ID"] = "32261789"
env_main["API_HASH"] = "06254a37741c127fd669909f57e67168"
env_main["SESSION_NAME"] = "berdiyorov"
p1 = subprocess.Popen([sys.executable, "main.py"], cwd="inst_main", env=env_main)

# 2. SIZNING ZAXIRA PROFILINGIZ (Auto-Commenter: .addkanal, .izoh)
p2 = subprocess.Popen([sys.executable, "commenter.py"])

# 3. DO'STINGIZNING PROFILI (Ham asosiy buyruqlar, ham o'zining Auto-Commenteri)
os.makedirs("inst_friend", exist_ok=True)
os.system("cp main.py inst_friend/ 2>/dev/null")
os.system("cp commenter_friend.py inst_friend/ 2>/dev/null")
os.system("cp friend.session inst_friend/ 2>/dev/null")
env_friend = os.environ.copy()
env_friend["API_ID"] = "31917495"
env_friend["API_HASH"] = "bc9a75239f98bc1858683dce6f4a1547"
env_friend["SESSION_NAME"] = "friend"

# Do'stingizning asosiy boti
p3 = subprocess.Popen([sys.executable, "main.py"], cwd="inst_friend", env=env_friend)
# Do'stingizning izoh boti
p4 = subprocess.Popen([sys.executable, "commenter_friend.py"], cwd="inst_friend", env=env_friend)

print(">>> Barcha botlar (Sizning asosiy, zaxira commenter va do'stingizning ikkala boti) ishga tushirildi! <<<")

p1.wait()
p2.wait()
p3.wait()
p4.wait()
