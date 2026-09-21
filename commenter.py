import asyncio
import json
import os
import random
import time
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, MsgIdInvalidError
from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest

API_ID = 5091449
API_HASH = "0b9ccd76f2d3b52fabb7617a458498e9"
SESSION_NAME = "commenter"
DB_FILE = "commenter_db.json"

DEFAULT_EMOJIS = ["🤣", "🥀", "🗿", "✅", "🤦‍♂️", "❌", "😭"]

def normalize_id(cid):
    """Har qanday formatdagi ID ni standart musbat songa keltiradi"""
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
    return {
        "channels": {},       # "clean_id": {"title": "...", "linked_id": ..., "comments": []}
        "log_chat": "me",
        "active": True,
        "sent_count": 0
    }

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(DB, f, indent=4, ensure_ascii=False)

DB = load_db()
BOT_START_TIME = time.time()
PROCESSED_POSTS = set()

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

async def setup_channel_internal(entity):
    try:
        full = await client(GetFullChannelRequest(entity))
        raw_cid = full.full_chat.id
        linked_id = full.full_chat.linked_chat_id
        
        if not linked_id:
            return None, None, "Ushbu kanalda izohlar (Discussion guruhi) ulanmagan!"

        # Muhokama guruhiga a'zo bo'lib qo'yish (izoh yozish huquqi bo'lishi uchun)
        try:
            await client(JoinChannelRequest(linked_id))
        except Exception:
            pass

        title = full.chats[0].title
        norm_id = str(normalize_id(raw_cid))

        return norm_id, linked_id, title
    except Exception as e:
        return None, None, str(e)

# ================= FAQAT KANAL POSTLARINI POYLASH =================
@client.on(events.NewMessage())
async def channel_post_listener(event):
    if not DB["active"]:
        return

    # Faqat va faqat kanaldagi xabarlar (guruhlar emas!)
    if not event.is_channel or event.is_group:
        return

    # Kanal ID tekshiruvi
    current_norm_id = str(normalize_id(event.chat_id))
    if current_norm_id not in DB["channels"]:
        return

    # Post takrorlanmasligini tekshirish
    post_key = f"{current_norm_id}_{event.id}"
    if post_key in PROCESSED_POSTS:
        return

    t0 = time.time()
    PROCESSED_POSTS.add(post_key)

    chan_data = DB["channels"][current_norm_id]
    pool = chan_data.get("comments") or DEFAULT_EMOJIS
    comment_text = random.choice(pool)

    # Kanal postining izohiga yozish
    try:
        # Telethon'ning to'g'ridan-to'g'ri kanal postiga izoh yozish funksiyasi
        # Bu avtomatik tarzda postning izohlar oynasiga (Discussion thread) yozadi
        await client.send_message(
            entity=event.chat_id,
            message=comment_text,
            comment_to=event.id
        )

        elapsed_ms = int((time.time() - t0) * 1000)
        DB["sent_count"] += 1
        save_db()

        if DB["log_chat"]:
            log_text = (
                f"⚡ **KANAL POSTIGA IZOH YOZILDI!**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📢 **Kanal:** `{chan_data.get('title', event.chat_id)}`\n"
                f"📝 **Post ID:** `{event.id}`\n"
                f"💬 **Izoh:** `{comment_text}`\n"
                f"⏱ **Tezlik:** `{elapsed_ms} ms`\n"
                f"📊 **Jami:** `{DB['sent_count']} ta`"
            )
            asyncio.create_task(client.send_message(DB["log_chat"], log_text))

    except MsgIdInvalidError:
        # Ba'zida kanal posti chiqqan zahoti muhokama xabari guruhda shakllanishi 0.2 soniya olishi mumkin
        try:
            await asyncio.sleep(0.3)
            discussion = await client.get_discussion_message(event.chat_id, event.id)
            await discussion.reply(comment_text)
            elapsed_ms = int((time.time() - t0) * 1000)
            DB["sent_count"] += 1
            save_db()
        except Exception as e:
            print(f"[Qayta urinishda xato]: {e}")

    except FloodWaitError as fw:
        await asyncio.sleep(fw.seconds)
    except Exception as err:
        print(f"[Izoh yozishda xatolik]: {err}")

# ================= BUYRUQLAR =================
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.ping$"))
async def handle_ping(event):
    start = time.time()
    msg = await event.edit("⚡ **Pinging...**")
    diff = (time.time() - start) * 1000
    await msg.edit(f"🏓 **Pong!**\n⚡ **Tezlik:** `{diff:.2f} ms`\n🚀 **Rejim:** `To'g'ridan-to'g'ri Kanal Izohi`")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.stat$"))
async def handle_stat(event):
    channels = DB.get("channels", {})
    if not channels:
        await event.edit("📭 Hozircha hech qanday kanal ulanmagan.")
        return

    text = f"📋 **KUZATILAYOTGAN KANALLAR ({len(channels)} ta):**\n━━━━━━━━━━━━━━━━━━━━\n"
    for i, (cid, data) in enumerate(channels.items(), 1):
        c_count = len(data.get("comments", []))
        izoh_info = f"`{c_count} ta maxsus izoh`" if c_count > 0 else "`standart emojilar`"
        text += f"{i}. **{data.get('title', 'Nomaʼlum')}**\n   🆔 `{cid}` | 💬 {izoh_info}\n"
    text += "━━━━━━━━━━━━━━━━━━━━"
    await event.edit(text)

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.addkanal(?: |$)(.*)"))
async def handle_addkanal(event):
    target = event.pattern_match.group(1).strip() or event.chat_id
    await event.edit("🔄 **Kanal tekshirilmoqda va ulanmoqda...**")
    try:
        entity = await client.get_entity(target)
        norm_id, linked_id, res = await setup_channel_internal(entity)
        if not norm_id:
            await event.edit(f"❌ **Xatolik:** {res}")
            return

        DB["channels"][norm_id] = {
            "title": res,
            "linked_id": linked_id,
            "comments": []
        }
        save_db()
        await event.edit(f"✅ **Kanal muvaffaqiyatli ulandi!**\n📢 **Nomi:** `{res}`\n🆔 **ID:** `{norm_id}`\n💬 Izohlar oynasi sozlandi.")
    except Exception as e:
        await event.edit(f"❌ **Kanal topilmadi:** {e}")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.delkanal(?: |$)(.*)"))
async def handle_delkanal(event):
    target = event.pattern_match.group(1).strip() or str(event.chat_id)
    try:
        ent = await client.get_entity(target)
        norm_id = str(normalize_id(ent.id))
    except Exception:
        norm_id = str(normalize_id(target))

    if norm_id in DB["channels"]:
        name = DB["channels"][norm_id].get("title", norm_id)
        del DB["channels"][norm_id]
        save_db()
        await event.edit(f"🗑 **Kanal o'chirildi:** `{name}`")
    else:
        await event.edit("⚠️ Ushbu kanal ro'yxatda topilmadi.")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.izoh(?: |$)(.*)"))
async def handle_izoh(event):
    content = event.pattern_match.group(1).strip()
    if "|" not in content:
        await event.edit("⚠️ Format: `.izoh @kanal | matn1 | matn2`")
        return
    parts = [p.strip() for p in content.split("|")]
    target, comments = parts[0], [c for c in parts[1:] if c]
    if not comments:
        await event.edit("⚠️ Kamida 1 ta izoh matni yozing!")
        return

    await event.edit("🔄 Sozlanmoqda...")
    try:
        entity = await client.get_entity(target)
        norm_id, linked_id, res = await setup_channel_internal(entity)
        if not norm_id:
            await event.edit(f"❌ {res}")
            return

        if norm_id not in DB["channels"]:
            DB["channels"][norm_id] = {"title": res, "linked_id": linked_id, "comments": comments}
        else:
            DB["channels"][norm_id]["comments"] = comments

        save_db()
        await event.edit(f"✅ **Maxsus izohlar biriktirildi!**\n📢 `{res}`: `{len(comments)} ta` variant.")
    except Exception as e:
        await event.edit(f"❌ Xatolik: {e}")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.log(?: |$)(.*)"))
async def handle_log(event):
    target = event.pattern_match.group(1).strip()
    if not target or target.lower() == "me":
        DB["log_chat"] = "me"
        save_db()
        await event.edit("📋 Log joyi: `Saved Messages`")
        return
    try:
        entity = await client.get_entity(int(target) if target.lstrip("-").isdigit() else target)
        DB["log_chat"] = entity.id
        save_db()
        await event.edit(f"📋 Log kanali: `{getattr(entity, 'title', entity.id)}`")
    except Exception as e:
        await event.edit(f"❌ Topilmadi: {e}")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.info$"))
async def handle_info(event):
    uptime_sec = int(time.time() - BOT_START_TIME)
    uptime_str = f"{uptime_sec // 3600} soat, {(uptime_sec % 3600) // 60} daqiqa"
    text = (
        f"📊 **AUTO-COMMENTER HOLATI**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **Kuzatuv:** `Faqat Kanal Postlari`\n"
        f"⏳ **Uptime:** `{uptime_str}`\n"
        f"🚀 **Yuborilgan izohlar:** `{DB['sent_count']} ta`\n"
        f"📢 **Ulangan kanallar:** `{len(DB['channels'])} ta`\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    await event.edit(text)

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.help$"))
async def handle_help(event):
    help_text = (
        "📖 **AUTO-COMMENTER BUYRUQLARI**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• `.ping` — Tezlikni tekshirish\n"
        "• `.stat` — Ulangan kanallar\n"
        "• `.addkanal <link>` — Kanalni ulash\n"
        "• `.delkanal <link>` — Kanalni o'chirish\n"
        "• `.izoh @kanal | m1 | m2` — Maxsus izohlar\n"
        "• `.log <me/id>` — Log joyini belgilash\n"
        "• `.info` — Tizim holati\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    await event.edit(help_text)

async def main():
    print(">>> Auto-Commenter ishga tushmoqda... <<<")
    await client.start()
    print(">>> Auto-Commenter faol! Kanallardagi yangi postlarni kutmoqda... <<<")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
