# Real Termux / Desktop Test Guide

After installing dependencies and configuring `.env`:

```bash
pip install -r requirements.txt
python tests_phase8.py
python tests_phase9.py
python tests_phase11.py
python tests_phase12.py
python tests_phase13.py
python main.py
```

## First smoke test in Telegram

1. `.help`
2. `.stat`
3. `.info`
4. `.ping`
5. Verify only the latest two normal interface responses remain.
6. `.on status`
7. `.on`
8. `.on status`
9. `.off`
10. `.off`

Do not test destructive `.del` with large values first. Start with a safe small test in a disposable Saved Messages context.

## Important

A real Telegram login and account actions cannot be honestly verified without your own credentials and a live Telegram session. Treat offline tests as code validation, not proof of every MTProto feature on every account.
