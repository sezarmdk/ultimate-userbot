# Phase 17 Fix Report

## 1. Block/Unblock AttributeError
Sabab: `ControlService.block()` `target.entity` ishlatgan, ammo `ResolvedTarget` ichida `entity` yo‘q edi.
Tuzatish: resolved target endi Telegram entity obyektini saqlaydi.

## 2. Control database migration
Sabab: eski jadvallarda `display_name` va `active` ustunlari yo‘q bo‘lishi mumkin edi.
Tuzatish: startup vaqtida ma'lumotni o‘chirmaydigan column migration qo‘shildi.

## 3. Autostatus parser
Sabab: avvalgi parser bo‘sh joy bilan ajratilgan bir nechta IDni bitta noto‘g‘ri qiymat sifatida qabul qilishi mumkin edi.
Tuzatish: ID, rejim va interval mustaqil parse qilinadi.

## 4. Bio restore source
Sabab: `get_me()` obyektida bio har doim mavjud emas.
Tuzatish: to‘liq user ma'lumoti so‘raladi.

## 5. Restart state restore
Saqlangan va faol Bio/Status workerlar restartdan keyin tiklanadi.
