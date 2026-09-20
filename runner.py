import subprocess
import os
import sys

# Render veb-portini ushlab turish
port = os.environ.get("PORT", "10000")
subprocess.Popen([sys.executable, "-m", "http.server", str(port)])

# Sizning profilingizni ishga tushirish
env1 = os.environ.copy()
env1["API_ID"] = "32261789"
env1["API_HASH"] = "06254a37741c127fd669909f57e67168"
env1["SESSION_NAME"] = "berdiyorov"

p1 = subprocess.Popen([sys.executable, "main.py"], env=env1)
p1.wait()
