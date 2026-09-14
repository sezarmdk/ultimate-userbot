# Phase 20 — Profile & Reliability Fix Report

- Emoji status now attempts a real Telethon MTProto request before claiming activation.
- If the installed API/account rejects the request, auto status remains disabled and the real reason is shown.
- Bio worker no longer silently swallows failures; errors are written to the database and cancellation remains safe.
- Story worker logs per-target failures without breaking the full worker.
- Delete scans now have a hard 20,000-message safety ceiling for very large chats.

No Telegram action is reported as successful without a confirmed request result.
