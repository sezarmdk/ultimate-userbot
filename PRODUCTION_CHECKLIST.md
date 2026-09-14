# Production Checklist

- [x] Exact 24 public command surface
- [x] SQLite WAL + integrity/quick checks
- [x] Required persistent tables
- [x] Duplicate command protection
- [x] Duplicate worker protection
- [x] Graceful shutdown guard
- [x] Secrets excluded from documentation/logging
- [x] Honest compatibility notes
- [x] Offline database smoke test

## Before real deployment
1. Install `requirements.txt`.
2. Create `.env` from `.env.example`.
3. Use your own Telegram API credentials.
4. Start once interactively and complete Telegram login.
5. Run `python tests_phase11.py`.
6. Use persistent storage for SQLite and the session.
