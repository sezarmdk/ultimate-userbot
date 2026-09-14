
# Telegram / API Compatibility Notes

- Telegram user accounts and MTProto capabilities vary by account, permissions and library version.
- Online presence cannot honestly guarantee 24/7 visibility.
- Story reactions and custom emoji behavior depend on current Telegram MTProto support and account capabilities.
- Some profile emoji-status operations may require Telegram Premium and compatible API methods.
- Message deletion depends on chat type and Telegram permissions.
- Blocking is a real Telegram account operation; failures must be reported rather than hidden.
- Autoread can only acknowledge messages where the account/API permits it.
- SQLite is local state; deployments need persistent storage to survive ephemeral filesystems.
- FloodWait is handled as a Telegram-imposed delay, not an instant retry.
