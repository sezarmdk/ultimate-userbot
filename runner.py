import subprocess
import os
import sys

# Render veb-port
port = os.environ.get("PORT", "10000")
subprocess.Popen([sys.executable, "-m", "http.server", str(port)])

# 1. SIZNING ASOSIY BOTINGIZ (berdiyorov.session)
env_main = os.environ.copy()
env_main["API_ID"] = "32261789"
env_main["API_HASH"] = "06254a37741c127fd669909f57e67168"
env_main["SESSION_NAME"] = "berdiyorov"
p1 = subprocess.Popen([sys.executable, "main.py"], env=env_main)

# 2. SIZNING ZAXIRA PROFILINGIZ (commenter.py)
p2 = subprocess.Popen([sys.executable, "commenter.py"])

# 3. DO'STINGIZNING TO'LIQ BOTI (friend_bot.py)
p3 = subprocess.Popen([sys.executable, "friend_bot.py"])

print(">>> Barcha 3 ta bot xavfsiz ishga tushirildi! <<<")

p1.wait()
p2.wait()
p3.wait()
