import asyncio
import datetime
import os
import re
import pytz
from telethon import TelegramClient, events
from telethon.tl.functions.account import UpdateEmojiStatusRequest
from telethon.tl.types import EmojiStatus, MessageEntityCustomEmoji

# ==================== SOZLAMALAR ====================
API_ID = int(os.environ.get("API_ID", "32261789"))
API_HASH = os.environ.get("API_HASH", "06254a37741c127fd669909f57e67168")
SESSION_NAME = os.environ.get("SESSION_NAME", "berdiyorov")
TIMEZONE = pytz.timezone("Asia/Tashkent")
# ====================================================

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# Tizim holati (State)
BOT_START_TIME = datetime.datetime.now(TIMEZONE)
STATE = {
    "auto_online": {
        "active": False,
        "chat_id": None,
        "task": None,
        "started_at": None
    },
    "auto_read": {
        "active": False,
        "started_at": None
    },
    "auto_status": {
        "active": False,
        "task": None,
        "emojis": [],
        "started_at": None
    },
    "muted_chats": set(),
    "muted_users": set(),
    "log_channel": None
}

def get_now_str():
    return datetime.datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

def format_uptime(start_dt):
    if not start_dt:
        return "Faol emas"
    diff = datetime.datetime.now(TIMEZONE) - start_dt
    days, seconds = diff.days, diff.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{days} kun, {hours} soat, {minutes} daqiqa, {seconds} soniya"

# ================= FON VAZIFALARI (LOOPS) =================
async def auto_online_loop(chat_id):
    """Har 20 soniyada joriy vaqtni yuborib, srazu o'chiradi."""
    while STATE["auto_online"]["active"]:
        try:
            now_time = datetime.datetime.now(TIMEZONE).strftime("%H:%M:%S")
            msg = await client.send_message(chat_id, f"🕒 `{now_time}`")
            await asyncio.sleep(0.5)
            await msg.delete()
        except Exception as e:
            print(f"[Auto-Online Xatosi]: {e}")
        await asyncio.sleep(20)

async def auto_status_loop(emoji_ids):
    """Har 5 soniyada Premium emoji statusni almashtirib turadi."""
    idx = 0
    while STATE["auto_status"]["active"]:
        try:
            current_id = emoji_ids[idx % len(emoji_ids)]
            await client(UpdateEmojiStatusRequest(
                emoji_status=EmojiStatus(document_id=current_id)
            ))
            idx += 1
        except Exception as e:
            print(f"[Auto-Status Xatosi]: {e}")
        await asyncio.sleep(5)

# ================= BUYRUQLAR (FAQAT SIZ UCHUN) =================

# 1. ONLINE SIGNAL (.on / .off)
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.on$"))
async def handle_on(event):
    if STATE["auto_online"]["active"]:
        await event.edit("⚠️ **Auto-Online allaqachon yoqilgan!**")
        return
    
    chat_id = event.chat_id
    STATE["auto_online"]["active"] = True
    STATE["auto_online"]["chat_id"] = chat_id
    STATE["auto_online"]["started_at"] = datetime.datetime.now(TIMEZONE)
    STATE["auto_online"]["task"] = asyncio.create_task(auto_online_loop(chat_id))
    await event.edit("✅ **Auto-Online yoqildi!**\nUshbu chatga har 20 soniyada vaqt yuborilib, srazu o'chiriladi.")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.off$"))
async def handle_off(event):
    if not STATE["auto_online"]["active"]:
        await event.edit("⚠️ **Auto-Online yoqilmagan.**")
        return
    
    STATE["auto_online"]["active"] = False
    if STATE["auto_online"]["task"]:
        STATE["auto_online"]["task"].cancel()
    STATE["auto_online"]["task"] = None
    STATE["auto_online"]["started_at"] = None
    await event.edit("🛑 **Auto-Online o'chirildi.**")

# 2. AUTO-READ (.read / .unread)
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.read$"))
async def handle_read(event):
    STATE["auto_read"]["active"] = True
    STATE["auto_read"]["started_at"] = datetime.datetime.now(TIMEZONE)
    await event.edit("👁 **Auto-Read yoqildi!**\nShaxsiy chatlardan kelgan barcha yangi xabarlar darhol o'qiladi.")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.unread$"))
async def handle_unread(event):
    STATE["auto_read"]["active"] = False
    STATE["auto_read"]["started_at"] = None
    await event.edit("🛑 **Auto-Read o'chirildi.**")

# 3. PING
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.ping$"))
async def handle_ping(event):
    start = datetime.datetime.now()
    msg = await event.edit("🏓 **Pinging...**")
    end = datetime.datetime.now()
    diff = (end - start).total_seconds() * 1000
    await msg.edit(f"🏓 **Pong!**\n⚡ **Tezlik:** `{diff:.2f} ms`\n📍 **Vaqt mintaqasi:** `Toshkent (UTC+5)`")

# 4. CALCULATOR (.c <ifoda>)
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.c (.+)"))
async def handle_calc(event):
    expr = event.pattern_match.group(1).strip()
    if not re.match(r"^[\d\s\+\-\*\/\(\)\.\,\%\*\*]+$", expr):
        await event.edit("⚠️ **Xatolik:** Ifodada faqat sonlar va arifmetik amallar bo'lishi kerak!")
        return
    try:
        result = eval(expr, {"__builtins__": None}, {})
        await event.edit(f"🧮 **Hisoblash:**\n`{expr}` = **`{result}`**")
    except Exception as err:
        await event.edit(f"❌ **Hisoblash xatosi:** `{err}`")

# 5. PREMIUM EMOJI STATUS (.astatus / .unstory)
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.astatus(?: |$)(.*)"))
async def handle_astatus(event):
    custom_ids = []
    if event.entities:
        for entity in event.entities:
            if isinstance(entity, MessageEntityCustomEmoji):
                custom_ids.append(entity.document_id)
    
    if not custom_ids:
        await event.edit("⚠️ **Xatolik:** Xabarda Premium Custom Emoji topilmadi!\nBuyruq yoniga Premium emojilarni yozing: `.astatus ⭐️ 🔥 ❤️`")
        return

    if STATE["auto_status"]["active"] and STATE["auto_status"]["task"]:
        STATE["auto_status"]["task"].cancel()

    STATE["auto_status"]["active"] = True
    STATE["auto_status"]["emojis"] = custom_ids
    STATE["auto_status"]["started_at"] = datetime.datetime.now(TIMEZONE)
    STATE["auto_status"]["task"] = asyncio.create_task(auto_status_loop(custom_ids))
    
    await event.edit(f"✨ **Auto-Status yoqildi!**\nJami: `{len(custom_ids)} ta` emoji tanildi.\nHar 5 soniyada yangilanadi.")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.unstory$"))
async def handle_unstory(event):
    if STATE["auto_status"]["active"]:
        STATE["auto_status"]["active"] = False
        if STATE["auto_status"]["task"]:
            STATE["auto_status"]["task"].cancel()
        STATE["auto_status"]["task"] = None
        STATE["auto_status"]["emojis"] = []
        STATE["auto_status"]["started_at"] = None

    try:
        await client(UpdateEmojiStatusRequest(emoji_status=EmojiStatus(document_id=0)))
        await event.edit("🛑 **Auto-Status to'xtatildi va profil emoji olib tashlandi.**")
    except Exception as e:
        await event.edit(f"🛑 **Status to'xtatildi, xatolik:** `{e}`")

# 6. LOG KANAL (.log <id/link>)
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.log(?: |$)(.*)"))
async def handle_log(event):
    target = event.pattern_match.group(1).strip()
    if not target:
        target = event.chat_id
    else:
        try:
            target = int(target)
        except ValueError:
            target = target.replace("https://t.me/", "")
    
    try:
        entity = await client.get_entity(target)
        STATE["log_channel"] = entity.id
        name = getattr(entity, "title", str(entity.id))
        await event.edit(f"📋 **Log kanali o'rnatildi:** `{name}` (`{entity.id}`)")
    except Exception as e:
        await event.edit(f"❌ **Kanal topilmadi:** `{e}`")

# 7. MUTE & UNMUTE (.mute / .unmute)
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.mute(?: |$)(.*)"))
async def handle_mute(event):
    target = event.pattern_match.group(1).strip()
    if not target:
        STATE["muted_chats"].add(event.chat_id)
        await event.edit("🔇 **Ushbu chat MUTE qilindi.**\nKelgan barcha xabarlar o'chiriladi.")
        return

    try:
        user_entity = await client.get_entity(int(target) if target.lstrip("-").isdigit() else target)
        STATE["muted_users"].add(user_entity.id)
        name = getattr(user_entity, "first_name", getattr(user_entity, "title", str(user_entity.id)))
        await event.edit(f"🔇 **Foydalanuvchi MUTE qilindi:** `{name}` (`{user_entity.id}`)")
    except Exception as e:
        await event.edit(f"❌ **Foydalanuvchi topilmadi:** `{e}`")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.unmute(?: |$)(.*)"))
async def handle_unmute(event):
    target = event.pattern_match.group(1).strip()
    if not target:
        if event.chat_id in STATE["muted_chats"]:
            STATE["muted_chats"].remove(event.chat_id)
            await event.edit("🔊 **Ushbu chat MUTE ro'yxatidan olindi.**")
        else:
            await event.edit("⚠️ **Bu chat mute qilinmagan.**")
        return

    try:
        user_entity = await client.get_entity(int(target) if target.lstrip("-").isdigit() else target)
        if user_entity.id in STATE["muted_users"]:
            STATE["muted_users"].remove(user_entity.id)
            await event.edit(f"🔊 **Foydalanuvchi UNMUTE qilindi:** `{user_entity.id}`")
        else:
            await event.edit("⚠️ **Ushbu foydalanuvchi mute ro'yxatida yo'q.**")
    except Exception as e:
        await event.edit(f"❌ **Xatolik:** `{e}`")

# 8. XABARLARNI O'CHIRISH (.del faqat o'zingizniki / .dell barcha tomonniki)
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.del(?: |$)(\d+)?"))
async def handle_del(event):
    count_str = event.pattern_match.group(1)
    limit = int(count_str) if count_str else 1
    
    await event.delete()
    
    deleted = 0
    to_delete = []
    async for msg in client.iter_messages(event.chat_id, from_user="me"):
        to_delete.append(msg.id)
        deleted += 1
        if deleted >= limit:
            break
            
    if to_delete:
        await client.delete_messages(event.chat_id, to_delete)

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.dell(?: |$)(\d+)?"))
async def handle_dell(event):
    count_str = event.pattern_match.group(1)
    limit = int(count_str) if count_str else 1
    
    await event.delete()
    
    to_delete = []
    async for msg in client.iter_messages(event.chat_id, limit=limit):
        to_delete.append(msg.id)
        
    if to_delete:
        await client.delete_messages(event.chat_id, to_delete)

# 9. TIZIM HAQIDA INFO (.info)
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.info$"))
async def handle_info(event):
    now_tashkent = get_now_str()
    bot_uptime = format_uptime(BOT_START_TIME)
    
    online_stat = "🔴 O'chirilgan"
    if STATE["auto_online"]["active"]:
        online_stat = f"🟢 Yoqilgan | Chat: `{STATE['auto_online']['chat_id']}` | Vaqt: {format_uptime(STATE['auto_online']['started_at'])}"
        
    read_stat = "🔴 O'chirilgan"
    if STATE["auto_read"]["active"]:
        read_stat = f"🟢 Yoqilgan | Vaqt: {format_uptime(STATE['auto_read']['started_at'])}"
        
    status_stat = "🔴 O'chirilgan"
    if STATE["auto_status"]["active"]:
        status_stat = f"🟢 Yoqilgan | Emojilar: `{len(STATE['auto_status']['emojis'])} ta` | Vaqt: {format_uptime(STATE['auto_status']['started_at'])}"

    log_stat = f"`{STATE['log_channel']}`" if STATE["log_channel"] else "O'rnatilmagan"
    muted_chats_count = len(STATE["muted_chats"])
    muted_users_count = len(STATE["muted_users"])

    info_text = f"""📊 **USERBOT TO'LIQ TIZIM MA'LUMOTLARI**
━━━━━━━━━━━━━━━━━━━━
🕒 **Hozirgi vaqt:** `{now_tashkent}` (Toshkent, UTC+5)
⏳ **Bot ish vaqti (Uptime):** `{bot_uptime}`

⚙️ **FUNKSIYALAR VA HOLATLAR:**
• **Auto-Online (20s):** {online_stat}
• **Auto-Read (PM):** {read_stat}
• **Auto-Status (5s):** {status_stat}
• **Log kanali:** {log_stat}
• **Muted chatlar:** `{muted_chats_count} ta`
• **Muted foydalanuvchilar:** `{muted_users_count} ta`
━━━━━━━━━━━━━━━━━━━━
💻 **Dastur:** `Telethon (Python 3)`
"""
    await event.edit(info_text)

# 10. YORDAM (.help)
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.help$"))
async def handle_help(event):
    help_text = """📖 **USERBOT BUYRUQLAR RO'YXATI**
━━━━━━━━━━━━━━━━━━━━
⚡ **Asosiy buyruqlar:**
• `.ping` — Bot tezligini tekshirish (ms).
• `.info` — Barcha funksiyalarning to'liq holati va Toshkent vaqti.
• `.help` — Ushbu buyruqlar ro'yxati.

🕒 **Online & O'qish:**
• `.on` — Yuborilgan chatga har 20 soniyada vaqt yozib srazu o'chiradi (Online saqlaydi).
• `.off` — Auto-Online rejimini o'chiradi.
• `.read` — Shaxsiydan kelgan xabarlarni darhol o'qilgan qiladi.
• `.unread` — Auto-Read rejimini o'chiradi.

✨ **Premium Emoji Status:**
• `.astatus <emoji1> <emoji2>` — Maxsus emoji statuslarni har 5 soniyada almashtiradi.
• `.unstory` — Emoji statusni to'xtatadi va bo'shatadi.

🗑 **Xabarlarni o'chirish:**
• `.del <son>` — Faqat siz yozgan xabarlardan berilgan sondagisini o'chiradi.
• `.dell <son>` — Ham siznikini, ham sherigingiznikini (umumiy) o'chiradi.

🔇 **Mute & Log:**
• `.log <kanal_id/link>` — O'chirilgan xabarlar boradigan kanalni belgilash.
• `.mute` — Yozilgan chatdagi hamma yangi xabarlarni o'chirib turadi.
• `.mute <id/user>` — Muayyan odamni mute qilish.
• `.unmute` yoki `.unmute <id>` — Mutedan chiqarish.

🧮 **Hisoblagich:**
• `.c <ifoda>` — Arifmetik misollarni hisoblaydi (Masalan: `.c 2+2*5`).
━━━━━━━━━━━━━━━━━━━━
"""
    await event.edit(help_text)

# ================= KELUVCHI XABARLAR NAZORATI =================
@client.on(events.NewMessage(incoming=True))
async def incoming_handler(event):
    if STATE["auto_read"]["active"] and event.is_private:
        try:
            await event.mark_read()
        except Exception:
            pass

    is_chat_muted = event.chat_id in STATE["muted_chats"]
    is_user_muted = event.sender_id in STATE["muted_users"]

    if is_chat_muted or is_user_muted:
        if STATE["log_channel"]:
            try:
                sender = await event.get_sender()
                sender_name = getattr(sender, "first_name", "Noma'lum")
                sender_id = event.sender_id
                chat_title = event.chat.title if (event.is_group or event.is_channel) else "Shaxsiy chat"
                
                log_msg = f"""🗑 **MUTE BO'LGAN XABAR TUTILDI:**
👤 **Kimdan:** {sender_name} (`{sender_id}`)
💬 **Chat:** {chat_title} (`{event.chat_id}`)
🕒 **Vaqt:** `{get_now_str()}`
📝 **Xabar matni:**
{event.raw_text}
"""
                await client.send_message(STATE["log_channel"], log_msg)
            except Exception as e:
                print(f"[Log yuborishda xato]: {e}")

        try:
            await event.delete()
        except Exception as e:
            print(f"[Xabarni o'chirishda xato]: {e}")

# ================= ISHGA TUSHIRISH =================
async def main():
    print("Userbot ishga tushmoqda...")
    await client.start()
    print(">>> Userbot muvaffaqiyatli ulandi va ishlamoqda! <<<")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
