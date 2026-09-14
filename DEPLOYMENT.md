
# Deployment Guide

## Termux
```bash
pkg update && pkg upgrade
pkg install python git
git clone <YOUR_REPOSITORY>
cd <YOUR_REPOSITORY>
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your own Telegram credentials
python main.py
```

Use a session process manager for long-running use. Android battery optimization may stop Termux background processes.

## Render
A long-running Telegram userbot requires a persistent worker/service. Render filesystem persistence and account/session handling must be configured carefully. Do not expose `.env`, session files, API hash, or session strings in logs or repositories.

Recommended:
- deploy as a worker, not a web service
- store secrets in Render environment variables
- use persistent storage if the deployment needs a local SQLite database/session file
- verify Render's current free/paid worker behavior before deployment

## GitHub
Never commit:
- `.env`
- session files
- SQLite databases containing personal state
- API hash
- session strings

```bash
git init
git add .
git status
git commit -m "Initial userbot"
git branch -M main
git remote add origin <YOUR_REPOSITORY_URL>
git push -u origin main
```
