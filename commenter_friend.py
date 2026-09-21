import asyncio
import json
import os
import random
import time
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, MsgIdInvalidError
from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest

API_ID = 31917495
API_HASH = "bc9a75239f98bc1858683dce6f4a1547"
SESSION_NAME = "friend"
DB_FILE = "commenter_friend_db.json"

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
            return None, None, "Ushbu kanalda izohlar (Discussion) ulanmagan!"

        try:
            await client(JoinChannelRequest(linked_id))
        except Exception:
            pass

        title = full.chats[0].title
        norm_id = str(normalize_id(raw_cid))
        return norm_id, linked_id, title
    except Exception as e:
        return None, None, str(e)

@client.on(events.NewMessage())
async def channel_post_listener(event):
    if not DB["active"] or not event.is_channel or event.is_group:
        return

    current_norm_id = str(normalize_id(event.chat_id))
    if current_norm_id not in DB["channels"]:
        return

    post_key = f"{current_norm_id}_{event.id}"
    if post_key in PROCESSED_POSTS:
        return

    t0 = time.time()
    PROCESSED_POSTS.add(post_key)

    chan_data = DB["channels"][current_norm_id]
    pool = chan_data.get("comments") or DEFAULT_EMOJIS
    comment_text = random.choice(pool)

    try:
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
                f"⚡ **[DO'STINGIZ] IZOH YOZILDI!**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📢 **Kanal:** `{chan_data.get('title', event.chat_id)}`\n"
                f"💬 **Izoh:** `{comment_text}`\n"
                f"⏱ **Tezlik:** `{elapsed_ms} ms`\n"
                f"📊 **Jami:** `{DB['sent_count']} ta`"
            )
            asyncio.create_task(client.send_message(DB["log_chat"], log_text))
    except MsgIdInvalidError:
        try:
            await asyncio.sleep(0.3)
            discussion = await client.get_discussion_message(event.chat_id, event.id)
            await discussion.reply(comment_text)
            elapsed_ms = int((time.time() - t0) * 1000)
            DB["sent_count"] += 1
            save_db()
        except Exception:
            pass
    except FloodWaitError as fw:
        await asyncio.sleep(fw.seconds)
    except Exception as err:
        print(f"[Do'stingiz commenter xatosi]: {err}")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.cstat$"))
async def handle_cstat(event):
    channels = DB.get("channels", {})
    if not channels:
        await event.edit("📭 Hozircha sizda izoh uchun kanal ulanmagan.\nQo'shish: `.cadd @kanal`")
        return
    text = f"📋 **[IZOH BOTI] ULANGAN KANALLAR ({len(channels)} ta):**\n━━━━━━━━━━━━━━━━━━━━\n"
    for i, (cid, data) in enumerate(channels.items(), 1):
        c_count = len(data.get("comments", []))
        izoh_info = f"`{c_count} ta maxsus`" if c_count > 0 else "`standart emojilar`"
        text += f"{i}. **{data.get('title', 'Nomaʼlum')}**\n   🆔 `{cid}` | 💬 {izoh_info}\n"
    text += "━━━━━━━━━━━━━━━━━━━━"
    await event.edit(text)

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.cadd(?: |$)(.*)"))
async def handle_cadd(event):
    target = event.pattern_match.group(1).strip() or event.chat_id
    await event.edit("🔄 Kanal ulanmoqda...")
    try:
        entity = await client.get_entity(target)
        norm_id, linked_id, res = await setup_channel_internal(entity)
        if not norm_id:
            await event.edit(f"❌ Xatolik: {res}")
            return
        DB["channels"][norm_id] = {"title": res, "linked_id": linked_id, "comments": []}
        save_db()
        await event.edit(f"✅ **Kanal ulandi!**\n📢 `{res}`\n💬 Standart emojilar faol.")
    except Exception as e:
        await event.edit(f"❌ Xatolik: {e}")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.cdel(?: |$)(.*)"))
async def handle_cdel(event):
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
        await event.edit(f"🗑 O'chirildi: `{name}`")
    else:
        await event.edit("⚠️ Ro'yxatda topilmadi.")

@client.on(events.NewMessage(outgoing=True, pattern=r"^\.cizoh(?: |$)(.*)"))
async def handle_cizoh(event):
    content = event.pattern_match.group(1).strip()
    if "|" not in content:
        await event.edit("⚠️ Format: `.cizoh @kanal | matn1 | matn2`")
        return
    parts = [p.strip() for p in content.split("|")]
    target, comments = parts[0], [c for c in parts[1:] if c]
    if not comments:
        await event.edit("⚠️ Kamida bitta matn yozing!")
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
        await event.edit(f"✅ Maxsus izohlar saqlandi!\n📢 `{res}`: `{len(comments)} ta` variant.")
    except Exception as e:
        await event.edit(f"❌ Xatolik: {e}")

async def main():
    print(">>> Do'stingizning Auto-Commenteri ishga tushmoqda... <<<")
    await client.start()
    print(">>> Do'stingizning Auto-Commenteri muvaffaqiyatli ulandi! <<<")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
