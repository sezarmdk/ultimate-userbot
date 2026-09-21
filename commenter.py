import asyncio
import json
import os
import random
import time
from telethon import TelegramClient, events
from telethon.tl.functions.messages import SendMessageRequest
from telethon.tl.types import InputReplyToMessage
from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest

API_ID = 5091449
API_HASH = "0b9ccd76f2d3b52fabb7617a458498e9"
SESSION_NAME = "commenter"
DB_FILE = "commenter_db.json"

DEFAULT_EMOJIS = ["🤣", "🥀", "🗿", "✅", "🤦‍♂️", "❌", "😭"]

def clean_id(cid):
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

# Tezlik uchun RAM kesh
INPUT_PEER_CACHE = {}

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

async def prewarm_channel(chan_id_str):
    """Keshni oldindan tayyorlash: Post kelganda 1 ms da jo'natish uchun"""
    try:
        data = DB["channels"].get(chan_id_str)
        if not data or not data.get("linked_id"):
            return
        linked_id = data["linked_id"]
        peer = await client.get_input_entity(linked_id)
        INPUT_PEER_CACHE[chan_id_str] = peer
    except Exception as e:
        print(f"[Kesh xatosi]: {e}")

async def setup_channel_internal(entity):
    try:
        full = await client(GetFullChannelRequest(entity))
        raw_cid = full.full_chat.id
        linked_id = full.full_chat.linked_chat_id
        
        if not linked_id:
            return None, None, "Ushbu kanalda izohlar (Discussion) guruhi ulanmagan!"

        try:
            await client(JoinChannelRequest(linked_id))
        except Exception:
            pass

        title = full.chats[0].title
        cid_clean = clean_id(raw_cid)
        
        # Peer ob'ektini oldindan keshlab olish
        peer = await client.get_input_entity(linked_id)
        INPUT_PEER_CACHE[cid_clean] = peer

        return cid_clean, linked_id, title
    except Exception as e:
        return None, None, str(e)

# ================= ULTRA TEZKOR POST TUTUVCHI =================
@client.on(events.NewMessage())
async def fast_comment_handler(event):
    if not DB["active"] or not event.is_channel or event.is_group:
        return

    post_key = f"{event.chat_id}_{event.id}"
    if post_key in PROCESSED_POSTS:
        return

    current_cid = clean_id(event.chat_id)
    if current_cid not in DB["channels"]:
        return

    # Post topildi — hisoblash boshlandi
    t0 = time.time()
    PROCESSED_POSTS.add(post_key)

    chan_data = DB["channels"][current_cid]
    pool = chan_data.get("comments") or DEFAULT_EMOJIS
    comment_text = random.choice(pool)

    # Keshdan to'g'ridan-to'g'ri InputPeer olish
    input_peer = INPUT_PEER_CACHE.get(current_cid)

    try:
        # Eng tezyurar MTProto to'g'ridan-to'g'ri so'rovi (Hech qanday keraksiz wrapperlarsiz)
        if input_peer:
            await client(SendMessageRequest(
                peer=input_peer,
                message=comment_text,
                reply_to=InputReplyToMessage(reply_to_msg_id=event.id),
                random_id=random.randint(0, 2**63 - 1)
            ))
        else:
            # Agar keshda yo'q bo'lsa (zaxira)
            await client.send_message(
                entity=event.chat_id,
                message=comment_text,
                comment_to=event.id
            )
            asyncio.create_task(prewarm_channel(current_cid))

        elapsed_ms = int((time.time() - t0) * 1000)
        DB["sent_count"] += 1
        save_db()

        if DB["log_chat"]:
            log_text = (
                f"⚡ **TEZKOR IZOH YUBORILDI!**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📢 **Kanal:** `{chan_data.get('title', event.chat_id)}`\n"
                f"💬 **Izoh:** `{comment_text}`\n"
                f"⏱ **Reaksiya tezligi:** `{elapsed_ms} ms`\n"
                f"📊 **Jami:** `{DB['sent_count']} ta`"
            )
            asyncio.create_task(client.send_message(DB["log_chat"], log_text))

    except Exception as err:
        # Agar kanal ichida muhokama posti biroz kechikayotgan bo'lsa fallback
        try:
            discussion_msg = await client.get_discussion_message(event.chat_id, event.id)
            await discussion_msg.reply(comment_text)
            elapsed_ms = int((time.time() - t0) * 1000)
            if DB["log_chat"]:
                asyncio.create_task(client.send_message(DB["log_chat"], f"⚡ Izoh (Fallback orqali): `{elapsed_ms} ms`"))
        except Exception as e:
            print(f"[Xatolik]: {e}")

# ================= BUYRUQLAR =================
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.ping$"))
async def handle_ping(event):
    start = time.time()
    msg = await event.edit("⚡ **Pinging...**")
    diff = (time.time() - start) * 1000
    await msg.edit(f"🏓 **Pong!**\n⚡ **Tezlik:** `{diff:.2f} ms`\n🚀 **Rejim:** `Ultra Fast MTProto`")

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
    await event.edit("🔄 **Kanal tekshirilmoqda va keshlanmoqda...**")
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
        await event.edit(f"✅ **Kanal ulandi va keshlandi!**\n📢 **Nomi:** `{res}`\n⚡ To'g'ridan-to'g'ri MTProto ulanishi yoqildi.")
    except Exception as e:
        await event.edit(f"❌ **Kanal topilmadi:** {e}")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.delkanal(?: |$)(.*)"))
async def handle_delkanal(event):
    target = event.pattern_match.group(1).strip() or str(event.chat_id)
    target_clean = clean_id(target)
    if target_clean in DB["channels"]:
        name = DB["channels"][target_clean].get("title", target_clean)
        del DB["channels"][target_clean]
        INPUT_PEER_CACHE.pop(target_clean, None)
        save_db()
        await event.edit(f"🗑 **Kanal o'chirildi:** `{name}`")
    else:
        await event.edit("⚠️ Ushbu kanal ro'yxatda yo'q.")

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

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.izoh(?: |$)(.*)"))
async def handle_izoh(event):
    content = event.pattern_match.group(1).strip()
    if "|" not in content:
        await event.edit("⚠️ Format: `.izoh @kanal | matn1 | matn2`")
        return
    parts = [p.strip() for p in content.split("|")]
    target, comments = parts[0], [c for c in parts[1:] if c]
    if not comments:
        await event.edit("⚠️ Kamida 1 ta izoh yozing!")
        return
    await event.edit("🔄 Sozlanmoqda...")
    try:
        entity = await client.get_entity(target)
        chan_id, linked_id, res = await setup_channel_internal(entity)
        if not chan_id:
            await event.edit(f"❌ {res}")
            return
        if chan_id not in DB["channels"]:
            DB["channels"][chan_id] = {"title": res, "linked_id": linked_id, "comments": comments}
        else:
            DB["channels"][chan_id]["comments"] = comments
        save_db()
        await event.edit(f"✅ Maxsus izohlar biriktirildi!\n📢 `{res}`: `{len(comments)} ta` variant.")
    except Exception as e:
        await event.edit(f"❌ Xatolik: {e}")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.info$"))
async def handle_info(event):
    uptime_sec = int(time.time() - BOT_START_TIME)
    uptime_str = f"{uptime_sec // 3600} soat, {(uptime_sec % 3600) // 60} daqiqa"
    text = (
        f"📊 **ULTRA-FAST AUTO-COMMENTER**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ **Rejim:** `Raw MTProto (Direct Peer)`\n"
        f"⏳ **Uptime:** `{uptime_str}`\n"
        f"🚀 **Yuborilgan izohlar:** `{DB['sent_count']} ta`\n"
        f"📢 **Ulangan kanallar:** `{len(DB['channels'])} ta`\n"
        f"⚡ **RAM Kesh holati:** `{len(INPUT_PEER_CACHE)} ta kanal tayyor`\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    await event.edit(text)

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.help$"))
async def handle_help(event):
    help_text = (
        "📖 **AUTO-COMMENTER BUYRUQLARI**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• `.ping` — Tezlikni o'lchash\n"
        "• `.stat` — Ulangan kanallar\n"
        "• `.addkanal <link>` — Kanalni ulash va keshga olish\n"
        "• `.delkanal <link>` — Kanalni o'chirish\n"
        "• `.izoh @kanal | m1 | m2` — Maxsus izohlar\n"
        "• `.log <me/id>` — Log joyini belgilash\n"
        "• `.info` — Tizim holati\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    await event.edit(help_text)

async def main():
    print(">>> Ultra-Fast Auto-Commenter ishga tushmoqda... <<<")
    await client.start()
    
    # Barcha mavjud kanallarni xotirada prewarm qilish
    for cid in DB.get("channels", {}):
        await prewarm_channel(cid)
        
    print(">>> Barcha kanallar keshlandi! Bot postlarni kutmoqda... <<<")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
