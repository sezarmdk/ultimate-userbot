# Phase 14 Fix Report

Real Telegram testidan aniqlangan muammolar:

- `.del 40` / `.del 60`: AttributeError
- `.story`: OperationalError

Aniq topilgan sabab:

`database/database.py` Story jadvalini minimal eski sxema bilan yaratgan, `StoryService` esa shu jadvalda `display_name`, `active`, statistika ustunlarini kutgan. `CREATE TABLE IF NOT EXISTS` eski jadvalni yangilamagani sababli OperationalError yuzaga kelgan.

Phase 14 yechimi:

- idempotent schema migration;
- eski `enabled` qiymatini yangi `active` qiymatiga ko‘chirish;
- yo‘q ustunlarni `ALTER TABLE` bilan qo‘shish;
- ma’lumotni o‘chirmaslik;
- startup vaqtida Story schema tekshiruvi.

`.del` uchun qo‘shimcha himoya:

- command message va progress message `exclude_ids` orqali o‘chirishdan himoyalandi;
- progress message ID tekshiriladi;
- ichki progress xatolari log qilinadi.

Offline testlar Telegram loginini tasdiqlamaydi. Real Telegram API testi Termux/kompyuterda dependency o‘rnatilgandan keyin bajariladi.
