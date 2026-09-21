import asyncio
import datetime
import json
import os
import random
import re
import time
import pytz
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, MsgIdInvalidError
from telethon.tl.functions.account import UpdateEmojiStatusRequest
from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest
from telethon.tl.types import EmojiStatus, MessageEntityCustomEmoji

API_ID = 31917495
API_HASH = "bc9a75239f98bc1858683dce6f4a1547"
SESSION_NAME = "friend"
TIMEZONE = pytz.timezone("Asia/Tashkent")
DB_FILE = "friend_commenter_db.json"

DEFAULT_EMOJIS = ["🤣", "🥀", "🗿", "✅", "🤦‍♂️", "❌", "😭"]

def normalize_id(cid):
    s = str(cid)
    if s.startswith("-100"):
        s = s[4:]
    elif s.startswith("-"):
        s = s[1:]
    return int(s)

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"channels": {}, "log_chat": "me", "active": True, "sent_count": 0}

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(DB, f, indent=4, ensure_ascii=False)

DB = load_db()
PROCESSED_POSTS = set()
BOT_START_TIME = datetime.datetime.now(TIMEZONE)

STATE = {
    "auto_online": {"active": False, "chat_id": None, "task": None, "started_at": None},
    "auto_read": {"active": False, "started_at": None},
    "auto_status": {"active": False, "task": None, "emojis": [], "started_at": None},
    "muted_chats": set(),
    "muted_users": set(),
    "log_channel": None
}

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

def get_now_str():
    return datetime.datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

def format_uptime(start_dt):
    if not start_dt:
        return "Faol emas"
    diff = datetime.datetime.now(TIMEZONE) - start_dt
    days, seconds = diff.days, diff.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{days} kun, {hours} soat, {minutes} daqiqa"

async def auto_online_loop(chat_id):
    while STATE["auto_online"]["active"]:
        try:
            now_time = datetime.datetime.now(TIMEZONE).strftime("%H:%M:%S")
            msg = await client.send_message(chat_id, f"🕒 `{now_time}`")
            await asyncio.sleep(0.5)
            await msg.delete()
        except Exception:
            pass
        await asyncio.sleep(20)

async def auto_status_loop(emoji_ids):
    idx = 0
    while STATE["auto_status"]["active"]:
        try:
            current_id = emoji_ids[idx % len(emoji_ids)]
            await client(UpdateEmojiStatusRequest(emoji_status=EmojiStatus(document_id=current_id)))
            idx += 1
        except Exception:
            pass
        await asyncio.sleep(5)

# ================= AUTO-COMMENTER QISMI =================
async def setup_channel_internal(entity):
    try:
        full = await client(GetFullChannelRequest(entity))
        raw_cid = full.full_chat.id
        linked_id = full.full_chat.linked_chat_id
        if not linked_id:
            return None, None, "Ushbu kanalda izohlar guruhi ulanmagan!"
        try:
            await client(JoinChannelRequest(linked_id))
        except Exception:
            pass
        return str(normalize_id(raw_cid)), linked_id, full.chats[0].title
    except Exception as e:
        return None, None, str(e)

@client.on(events.NewMessage())
async def friend_channel_post_listener(event):
    if not DB["active"] or not event.is_channel or event.is_group:
        return
    c_id = str(normalize_id(event.chat_id))
    if c_id not in DB["channels"]:
        return
    post_key = f"{c_id}_{event.id}"
    if post_key in PROCESSED_POSTS:
        return
    PROCESSED_POSTS.add(post_key)
    
    chan_data = DB["channels"][c_id]
    pool = chan_data.get("comments") or DEFAULT_EMOJIS
    comment_text = random.choice(pool)

    try:
        await client.send_message(entity=event.chat_id, message=comment_text, comment_to=event.id)
        DB["sent_count"] += 1
        save_db()
    except MsgIdInvalidError:
        try:
            await asyncio.sleep(0.3)
            disc = await client.get_discussion_message(event.chat_id, event.id)
            await disc.reply(comment_text)
            DB["sent_count"] += 1
            save_db()
        except Exception:
            pass
    except Exception as err:
        print(f"[Do'stingiz commenter xatosi]: {err}")

# ================= ASOSIY BUYRUQLAR =================
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.ping$"))
async def handle_ping(event):
    s = time.time()
    msg = await event.edit("🏓 **Pinging...**")
    diff = (time.time() - s) * 1000
    await msg.edit(f"🏓 **Pong!**\n⚡ **Tezlik:** `{diff:.2f} ms`")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.on$"))
async def handle_on(event):
    if STATE["auto_online"]["active"]:
        await event.edit("⚠️ Auto-Online yoqilgan!")
        return
    STATE["auto_online"]["active"] = True
    STATE["auto_online"]["chat_id"] = event.chat_id
    STATE["auto_online"]["started_at"] = datetime.datetime.now(TIMEZONE)
    STATE["auto_online"]["task"] = asyncio.create_task(auto_online_loop(event.chat_id))
    await event.edit("✅ **Auto-Online yoqildi!**")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.off$"))
async def handle_off(event):
    STATE["auto_online"]["active"] = False
    if STATE["auto_online"]["task"]:
        STATE["auto_online"]["task"].cancel()
    await event.edit("🛑 **Auto-Online o'chirildi.**")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.read$"))
async def handle_read(event):
    STATE["auto_read"]["active"] = True
    await event.edit("👁 **Auto-Read yoqildi!**")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.unread$"))
async def handle_unread(event):
    STATE["auto_read"]["active"] = False
    await event.edit("🛑 **Auto-Read o'chirildi.**")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.del(?: |$)(\d+)?"))
async def handle_del(event):
    limit = int(event.pattern_match.group(1) or 1)
    await event.delete()
    to_del = [m.id async for m in client.iter_messages(event.chat_id, from_user="me")][:limit]
    if to_del:
        await client.delete_messages(event.chat_id, to_del)

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.(?:addkanal|cadd)(?: |$)(.*)"))
async def handle_cadd(event):
    target = event.pattern_match.group(1).strip() or event.chat_id
    await event.edit("🔄 Kanal tekshirilmoqda...")
    nid, lid, title = await setup_channel_internal(target)
    if not nid:
        await event.edit(f"❌ Xatolik: {title}")
        return
    DB["channels"][nid] = {"title": title, "linked_id": lid, "comments": []}
    save_db()
    await event.edit(f"✅ **Kanal ulandi!**\n📢 `{title}`\n💬 Standart emojilar faol.")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.(?:delkanal|cdel)(?: |$)(.*)"))
async def handle_cdel(event):
    target = event.pattern_match.group(1).strip() or str(event.chat_id)
    try:
        ent = await client.get_entity(target)
        nid = str(normalize_id(ent.id))
    except Exception:
        nid = str(normalize_id(target))
    if nid in DB["channels"]:
        t = DB["channels"][nid].get("title", nid)
        del DB["channels"][nid]
        save_db()
        await event.edit(f"🗑 O'chirildi: `{t}`")
    else:
        await event.edit("⚠️ Kanal ro'yxatda topilmadi.")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.(?:stat|cstat)$"))
async def handle_cstat(event):
    ch = DB.get("channels", {})
    if not ch:
        await event.edit("📭 Hech qanday kanal ulanmagan.\nQo'shish: `.cadd @kanal`")
        return
    text = f"📋 **KUZATUV KANALLARI ({len(ch)} ta):**\n"
    for i, (cid, d) in enumerate(ch.items(), 1):
        text += f"{i}. **{d.get('title')}** (`{cid}`)\n"
    await event.edit(text)

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.help$"))
async def handle_help(event):
    await event.edit("""📖 **BUYRUQLAR:**
• `.ping` — Tezlik
• `.on` / `.off` — Auto-Online
• `.read` / `.unread` — Auto-Read
• `.del <son>` — Xabarlarni o'chirish
• `.addkanal <link>` (yoki `.cadd`) — Kanalni ulash
• `.izoh @kanal | matn1 | matn2` — Kanalga maxsus izohlar qo'shish
• `.stat` (yoki `.cstat`) — Ulangan kanallar ro'yxati
• `.delkanal <link>` — Kanalni uzish
• `.cdel <link>` — Kanalni uzish
• `.cstat` — Ulangan kanallar
""")

@client.on(events.NewMessage(incoming=True))
async def handle_inc(event):
    if STATE["auto_read"]["active"] and event.is_private:
        try:
            await event.mark_read()
        except Exception:
            pass

async def main():
    print(">>> Do'stingizning to'liq boti ishga tushmoqda... <<<")
    await client.start()
    print(">>> Do'stingizning boti faol! <<<")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
