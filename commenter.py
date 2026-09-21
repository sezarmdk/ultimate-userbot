import asyncio
import json
import os
import random
import time
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest

API_ID = 5091449
API_HASH = "0b9ccd76f2d3b52fabb7617a458498e9"
SESSION_NAME = "commenter"
DB_FILE = "commenter_db.json"

DEFAULT_EMOJIS = ["🤣", "🥀", "🗿", "✅", "🤦‍♂️", "❌", "😭"]

def clean_id(cid):
    """ID larni tozalab, bir xil formatga keltirish"""
    s = str(cid)
    if s.startswith("-100"):
        return s[4:]
    if s.startswith("-"):
        return s[1:]
    return s

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "channels": {},
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
            return None, None, "Ushbu kanalda izohlar (Discussion) guruhi ulanmagan!"

        # Muhokama guruhiga oldindan a'zo bo'lish
        try:
            await client(JoinChannelRequest(linked_id))
        except Exception:
            pass

        title = full.chats[0].title
        return clean_id(raw_cid), linked_id, title
    except Exception as e:
        return None, None, str(e)

# ================= KANAL POSTLARINI TUTISH =================
@client.on(events.NewMessage())
async def fast_comment_handler(event):
    if not DB["active"] or not event.is_channel or event.is_group:
        return

    post_key = f"{event.chat_id}_{event.id}"
    if post_key in PROCESSED_POSTS:
        return

    current_cid = clean_id(event.chat_id)
    
    # Kanal bazada bormi?
    if current_cid not in DB["channels"]:
        return

    PROCESSED_POSTS.add(post_key)
    start_time = time.time()

    chan_data = DB["channels"][current_cid]
    
    # Izoh tanlash
    pool = chan_data.get("comments")
    if not pool:
        pool = DEFAULT_EMOJIS
    comment_text = random.choice(pool)

    # Izoh yuborish (Avval to'g'ridan-to'g'ri, agar topilmasa get_discussion_message orqali)
    try:
        try:
            await client.send_message(
                entity=event.chat_id,
                message=comment_text,
                comment_to=event.id
            )
        except Exception:
            # Agar comment_to kanal entitysida ishlamasa, muhokama guruhiga reply qilamiz
            discussion_msg = await client.get_discussion_message(event.chat_id, event.id)
            await discussion_msg.reply(comment_text)

        elapsed_ms = int((time.time() - start_time) * 1000)
        DB["sent_count"] += 1
        save_db()

        if DB["log_chat"]:
            try:
                log_text = (
                    f"⚡ **TEZKOR IZOH YUBORILDI!**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📢 **Kanal:** `{chan_data.get('title', event.chat_id)}`\n"
                    f"💬 **Izoh:** `{comment_text}`\n"
                    f"⏱ **Tezlik:** `{elapsed_ms} ms`\n"
                    f"📊 **Jami izohlar:** `{DB['sent_count']} ta`"
                )
                await client.send_message(DB["log_chat"], log_text)
            except Exception:
                pass

    except FloodWaitError as fw:
        print(f"[FloodWait]: {fw.seconds} soniya kutiladi...")
        await asyncio.sleep(fw.seconds)
    except Exception as err:
        print(f"[Izoh yozishda xatolik]: {err}")

# ================= BUYRUQLAR =================
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.ping$"))
async def handle_ping(event):
    start = time.time()
    msg = await event.edit("⚡ **Pinging...**")
    diff = (time.time() - start) * 1000
    await msg.edit(f"🏓 **Pong!**\n⚡ **Tezlik:** `{diff:.2f} ms`\n🚀 **Status:** `Aktiv`")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.stat$"))
async def handle_stat(event):
    channels = DB.get("channels", {})
    if not channels:
        await event.edit("📭 **Hozircha hech qanday kanal ulanmagan.**\nQo'shish: `.addkanal @kanal`")
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
    target = event.pattern_match.group(1).strip()
    if not target:
        target = event.chat_id

    await event.edit("🔄 **Kanal tekshirilmoqda va ulanmoqda...**")
    try:
        entity = await client.get_entity(target)
        chan_id, linked_id, res = await setup_channel_internal(entity)
        if not chan_id:
            await event.edit(f"❌ **Xatolik:** {res}")
            return

        DB["channels"][chan_id] = {
            "title": res,
            "linked_id": linked_id,
            "comments": []
        }
        save_db()
        await event.edit(f"✅ **Kanal muvaffaqiyatli ulandi!**\n📢 **Nomi:** `{res}`\n🆔 **ID:** `{chan_id}`\n💬 Standart emojilar faollashdi.")
    except Exception as e:
        await event.edit(f"❌ **Kanal topilmadi:** `{e}`")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.delkanal(?: |$)(.*)"))
async def handle_delkanal(event):
    target = event.pattern_match.group(1).strip()
    if not target:
        target = str(event.chat_id)
    else:
        try:
            ent = await client.get_entity(target)
            target = str(ent.id)
        except Exception:
            target = str(target)

    target_clean = clean_id(target)

    if target_clean in DB["channels"]:
        name = DB["channels"][target_clean].get("title", target_clean)
        del DB["channels"][target_clean]
        save_db()
        await event.edit(f"🗑 **Kanal olib tashlandi:** `{name}`")
    else:
        await event.edit("⚠️ **Ushbu kanal ro'yxatda topilmadi.**")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.log(?: |$)(.*)"))
async def handle_log(event):
    target = event.pattern_match.group(1).strip()
    if not target or target.lower() == "me":
        DB["log_chat"] = "me"
        save_db()
        await event.edit("📋 **Log joyi:** `Saved Messages`")
        return

    try:
        entity = await client.get_entity(int(target) if target.lstrip("-").isdigit() else target)
        DB["log_chat"] = entity.id
        save_db()
        title = getattr(entity, "title", str(entity.id))
        await event.edit(f"📋 **Log kanali:** `{title}`")
    except Exception as e:
        await event.edit(f"❌ **Topilmadi:** `{e}`")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.izoh(?: |$)(.*)"))
async def handle_izoh(event):
    content = event.pattern_match.group(1).strip()
    if "|" not in content:
        await event.edit("⚠️ **Format:**\n`.izoh @kanal | 1-matn | 2-matn`")
        return

    parts = [p.strip() for p in content.split("|")]
    target = parts[0]
    comments = [c for c in parts[1:] if c]

    if not comments:
        await event.edit("⚠️ Kamida bitta izoh matni yozing!")
        return

    await event.edit("🔄 **Kanal sozlanmoqda...**")
    try:
        entity = await client.get_entity(target)
        chan_id, linked_id, res = await setup_channel_internal(entity)
        if not chan_id:
            await event.edit(f"❌ **Xatolik:** {res}")
            return

        if chan_id not in DB["channels"]:
            DB["channels"][chan_id] = {
                "title": res,
                "linked_id": linked_id,
                "comments": comments
            }
        else:
            DB["channels"][chan_id]["comments"] = comments

        save_db()
        await event.edit(
            f"✅ **Maxsus izohlar saqlandi!**\n"
            f"📢 **Kanal:** `{res}`\n"
            f"📝 **Izohlar soni:** `{len(comments)} ta`"
        )
    except Exception as e:
        await event.edit(f"❌ **Xatolik:** `{e}`")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.info$"))
async def handle_info(event):
    uptime_sec = int(time.time() - BOT_START_TIME)
    uptime_str = f"{uptime_sec // 3600} soat, {(uptime_sec % 3600) // 60} daqiqa"
    status = "🟢 Faol" if DB["active"] else "🔴 To'xtatilgan"
    log_target = "Saved Messages" if DB["log_chat"] == "me" else f"`{DB['log_chat']}`"

    text = f"""📊 **TEZKOR IZOH USERBOTI (AUTO-COMMENTER)**
━━━━━━━━━━━━━━━━━━━━
⚙️ **Holat:** {status}
⏳ **Uptime:** `{uptime_str}`
🚀 **Jami yuborilgan izohlar:** `{DB['sent_count']} ta`
📢 **Ulangan kanallar:** `{len(DB['channels'])} ta`
📋 **Log joyi:** {log_target}
━━━━━━━━━━━━━━━━━━━━
"""
    await event.edit(text)

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.help$"))
async def handle_help(event):
    help_text = """📖 **TEZKOR IZOH USERBOT BUYRUQLARI**
━━━━━━━━━━━━━━━━━━━━
⚡ **Buyruqlar:**
• `.ping` — Bot tezligini tekshirish.
• `.stat` — Ulangan kanallar ro'yxati.
• `.addkanal <link>` — Kanalni ulash.
• `.delkanal <link>` — Kanalni uzish.
• `.izoh @kanal | matn1 | matn2` — Kanalga maxsus matnlar biriktirish.
• `.log <link/me>` — Hisobotlar boradigan joy.
• `.info` — Tizim holati.
━━━━━━━━━━━━━━━━━━━━
"""
    await event.edit(help_text)

async def main():
    print(">>> Auto-Commenter ishga tushmoqda... <<<")
    await client.start()
    print(">>> Auto-Commenter muvaffaqiyatli ulandi va ishlamoqda! <<<")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
