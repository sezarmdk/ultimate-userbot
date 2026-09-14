# Бeрдиёров JARVIS Userbot v1.0 — Phase 17 Fixed

## Phase 17: Haqiqiy command audit va mustahkamlash

Bu versiyada oldingi buildlardan qolgan bir nechta real mantiqiy xato tuzatildi.

### Tuzatildi

- `ResolvedTarget` endi haqiqiy Telegram entity obyektini ham saqlaydi. Shu sabab `.block` va `.unblock` ichidagi `target.entity` AttributeError muammosi tuzatildi.
- Target resolver endi `@username`, oddiy username, raqamli ID va oddiy `t.me/username` havolasini normalizatsiya qiladi.
- Eski `muted_targets` va `blocked_targets` jadvallari ma'lumot o‘chirilmasdan avtomatik migration qilinadi.
- `.autostatus` parser qayta yozildi: bir nechta ID, `random`, `sequence` va `: interval` aniq tekshiriladi.
- Bio olish `get_me().about` ga tayanmaydi; to‘liq foydalanuvchi ma'lumoti orqali olinadi.
- Restartdan keyin saqlangan Bio/Status worker holatlari tiklanadi, duplicate worker yaratilmaydi.
- `main.py` dagi qolib ketgan asosiy inglizcha interface matnlari o‘zbekchalashtirildi.
- Owner nomi standart ravishda **Бeрдиёров**.

## Muhim halol cheklovlar

- Story API va emoji status API builddagi Telethon qatlamida tasdiqlanmagan bo‘lsa, userbot muvaffaqiyatni soxtalashtirmaydi.
- Real Telegram account testi bu build tayyorlangan muhitda bajarilmagan. Termux yoki kompyuterda dependency o‘rnatib test qilish kerak.

## O‘rnatish

```bash
pkg update -y
pkg install python git unzip -y
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python tests_phase17.py
python main.py
```

API_ID va API_HASH ni hech kimga yubormang.

## Phase 17 birinchi testlari

Telegram ichida:

```text
.help
.stat
.ping
.calc 2^10
.autostatus 111 222 sequence : 60
.mute status
.block @username
.del 1
.story status
```

Har bir real xato uchun screenshot yoki to‘liq traceback asosida keyingi tuzatish qilinadi.
