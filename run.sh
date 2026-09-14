#!/bin/bash
# Render portini ushlab turish (UptimeRobot uchun)
python -m http.server $PORT &

# 1-profil: Sizning profilingiz
python main.py &

# 2-profil: Do'stingizning profili (alohida DB va alohida sessiya bilan)
SESSION_NAME=friend API_ID=31917495 API_HASH=bc9a75239f98bc1858683dce6f4a1547 DATABASE_PATH=friend.db python main.py &

wait -n
exit $?
