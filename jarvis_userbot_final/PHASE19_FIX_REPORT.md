# Phase 19 — Real Audit Fixes

## Fixed
- `.story check` no longer falls through into normal target-add logic when Story API support becomes available.
- Edit tracker failures are logged to the database instead of being silently discarded.
- Incoming-message edit cache is capped at 5000 entries to prevent unbounded memory growth.
- Additional visible UI strings were translated to Uzbek (`Guruhlar`, `Kanallar`, `Qamrov`, `Tarix`, log connection fields).

## Honest compatibility note
Story fetching/reactions and emoji status remain dependent on the installed Telethon/MTProto layer and account capability. This build does not claim those actions succeeded unless a confirmed Telegram API request succeeds.
