# Phase 21 Fix Report

## Tuzatildi
- `.unblock` endi Telegram server amali muvaffaqiyatli bo‘lsa, eski mahalliy qayd bo‘lmagani sababli soxta "bloklanmagan" javob qaytarmaydi.
- Block/unblock xatolari markaziy error logga yoziladi.
- `State` ko‘rinishidagi qolib ketgan inglizcha UI `Holat`ga almashtirildi.
- `target.entity` bilan ishlash va Telegram amali tasdiqlanishi saqlab qolindi.

## Halol compatibility
Block/Unblock Telethon MTProto orqali haqiqiy server so‘rovini yuboradi. Akkaunt ruxsati yoki Telegram xatosi bo‘lsa muvaffaqiyat ko‘rsatilmaydi.
