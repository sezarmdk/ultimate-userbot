import asyncio
import time
import signal

from telethon import TelegramClient, events

from config.settings import load_settings
from database.database import Database
from core.registry import Command, CommandRegistry
from core.parser import parse_command
from core.typo_engine import TypoEngine
from core.cleanup import ResponseCleanup
from core.target_resolver import TargetResolver, TargetNotFound
from services.response_history import ResponseHistoryService
from services.story_service import StoryService
from services.autoread_service import AutoreadService
from services.edit_service import EditService
from services.logger_service import LoggerService
from services.control_service import ControlService
from services.profile_service import ProfileService, RotationState
from services.calculator_service import SafeCalculator, CalculatorError
from services.delete_service import DeleteService
from services.system_service import SystemService
from workers.story import StoryWorker
from workers.manager import WorkerManager, WorkerState
from workers.online import OnlineWorker
from ui.formatter import UI


class App:
    def __init__(self):
        self.settings = load_settings()
        self.client = TelegramClient(
            self.settings.session_name,
            self.settings.api_id,
            self.settings.api_hash,
        )
        self.db = Database(self.settings.database_path)
        self.registry = CommandRegistry()
        self.workers = WorkerManager()
        self.response_history = None
        self.cleanup = None
        self.targets = TargetResolver(self.client)
        self.story = None
        self.autoread = None
        self.edits = None
        self.logger = None
        self.control = None
        self.profile = None
        self.calculator = SafeCalculator()
        self.deleter = None
        self.started_at = time.monotonic()
        self.system = None
        self._shutdown_requested = False
        self.original_messages = {}  # runtime cache for edit comparison
        self.owner_name = self.settings.owner_name  # safe fallback until real profile loads

    @staticmethod
    def _derive_owner_name(me, fallback: str) -> str:
        """Build a display name straight from the connected Telegram profile,
        so the bot always addresses whoever's account it is running on."""
        first = (getattr(me, "first_name", None) or "").strip()
        last = (getattr(me, "last_name", None) or "").strip()
        full = f"{first} {last}".strip()
        if full:
            return full
        username = (getattr(me, "username", None) or "").strip()
        if username:
            return f"@{username}"
        return fallback

    def command(self, name, description, category, aliases=(), examples=()):
        def decorator(handler):
            self.registry.register(Command(
                name=name, description=description, category=category,
                handler=handler, aliases=tuple(aliases), examples=tuple(examples)
            ))
            return handler
        return decorator

    async def reply(self, event, text, response_type="temporary"):
        message = await event.respond(text, parse_mode="md")
        await self.cleanup.add(event.chat_id, message.id, response_type)
        return message

    def register_commands(self):
        @self.command("help", "Buyruqlar bo‘limlarini ko‘rsatish", "control")
        async def help_command(event, parsed):
            section = parsed.args[0].lower() if parsed.args else None
            if section == "system":
                body = "` .on` — online connection worker\n`.off` — stop online worker\n`.ping` `.info` `.stat`"
            else:
                body = (
                    "📡 **SYSTEM**\n`.on` `.off` `.ping` `.info`\n\n"
                    "👁 **TRACKING**\n`.story` `.unstory` `.taxrir` `.untaxrir`\n\n"
                    "📖 **AUTOMATION**\n`.autoread` `.autoreadall` `.unread`\n\n"
                    "👤 **CONTROL**\n`.mute` `.unmute` `.block` `.unblock`\n\n"
                    "✨ **PROFILE**\n`.autostatus` `.unstatus` `.bio` `.unbio`\n\n"
                    "🛠 **TOOLS**\n`.calc` `.del`\n\n"
                    "⚙️ **CONTROL**\n`.log` `.stat` `.help`"
                )
            await self.reply(event, UI.info("USERBOT BOSHQARUVI", body) + UI.ready(self.owner_name), "help")

        @self.command("on", "Start real online connection worker", "system")
        async def on_command(event, parsed):
            mode = parsed.args[0].lower() if parsed.args else "start"
            info = self.workers.status("online_worker")

            if mode in {"status", "info"}:
                state = info.state.value if info else "stopped"
                started = info.started_at.isoformat() if info and info.started_at else "—"
                await self.reply(event, UI.info(
                    "ONLAYN TIZIM HOLATI",
                    f"📡 **Holat**\n{state.title()}\n\n⏱ **Boshlangan vaqt**\n{started}\n\n"
                    "ℹ️ Bu holat ishchining haqiqiy ulanish holatini ko‘rsatadi. Telegramdagi ko‘rinadigan onlaynlik 24/7 kafolat qilinmaydi."
                ), "result")
                return

            if mode == "help":
                await self.reply(event, UI.info(
                    "ONLAYN TIZIM YORDAMI",
                    "`.on` — onlayn ulanish ishchisini yoqish\n`.on status` — holatni ko‘rish\n`.off` — faqat shu ishchini to‘xtatish"
                ), "help")
                return

            worker = OnlineWorker(self.client)
            info, started = await self.workers.start("online_worker", worker.run)
            if not started:
                await self.reply(event, UI.info(
                    "ONLAYN TIZIM ALLAQACHON FAOL",
                    f"📡 **Holat**\nFaol\n\n🔄 **Ishchi**\nSog‘lom"
                ) + UI.ready(self.owner_name), "result")
                return

            await self.reply(event, UI.success(
                "ONLAYN ULASH TIZIMI FAOL",
                "📡 **Ulanish ishchisi**\nIshlamoqda\n\n"
                "🔄 **Takrorlanishdan himoya**\nFaol\n\n"
                "ℹ️ Ishchi haqiqiy MTProto ulanishini saqlaydi. Telegram ko‘rinadigan onlaynlik holatini o‘zi boshqaradi."
            ) + UI.ready(self.owner_name), "result")

        @self.command("off", "Stop only online worker", "system")
        async def off_command(event, parsed):
            stopped = await self.workers.stop("online_worker")
            if not stopped:
                await self.reply(event, UI.info(
                    "ONLAYN TIZIM ALLAQACHON TO‘XTAGAN",
                    "📡 Faol onlayn ishchi topilmadi."
                ), "result")
                return
            await self.reply(event, UI.info(
                "ONLAYN TIZIM TO‘XTATILDI",
                "🔴 **Onlayn ishchi**\nTo‘xtatildi\n\n"
                "Boshqa doimiy funksiyalar `.off` tomonidan o‘zgartirilmaydi."
            ) + UI.ready(self.owner_name), "result")

        @self.command("ping", "Measure meaningful local latency", "system")
        async def ping_command(event, parsed):
            t0 = time.perf_counter()
            message = await self.reply(event, UI.loading("TIZIM KECHIKISHI", "Tasdiqlangan mahalliy ko‘rsatkichlar o‘lchanmoqda..."), "progress")
            db_ms = None
            telegram_ms = None
            try:
                d0 = time.perf_counter()
                assert self.db.conn
                async with self.db.conn.execute("SELECT 1") as cursor:
                    await cursor.fetchone()
                db_ms = (time.perf_counter() - d0) * 1000
            except Exception:
                pass
            try:
                tg0 = time.perf_counter()
                await self.client.get_me()
                telegram_ms = (time.perf_counter() - tg0) * 1000
            except Exception:
                telegram_ms = None
            processing = (time.perf_counter() - t0) * 1000
            body = f"⚡ **Qayta ishlash**\n`{processing:.2f} ms`\n\n"
            body += f"💾 **Ma’lumotlar bazasi**\n`{db_ms:.2f} ms`\n\n" if db_ms is not None else "💾 **Ma’lumotlar bazasi**\nMavjud emas\n\n"
            body += (f"🌐 **Telegram**\n`{telegram_ms:.2f} ms` — `get_me` so‘rovi asosida."
                     if telegram_ms is not None else
                     "🌐 **Telegram**\nO‘lchanmadi — soxta tarmoq kechikishi ko‘rsatilmaydi.")
            await message.edit(UI.success("TIZIM KECHIKISHI", body))
            await self.cleanup.finalize(event.chat_id, message.id, "result")

        @self.command("info", "Tizim ma'lumotlarini ko'rsatish", "system")
        async def info_command(event, parsed):
            integrity = await self.db.integrity_check()
            uptime = int(time.monotonic() - self.started_at)
            workers = sum(1 for w in self.workers.all_status() if w.state == WorkerState.RUNNING)
            await self.reply(event, UI.info(
                "USERBOT MA’LUMOTLARI",
                f"🤖 **Versiya**\nБeрдиёров JARVIS Userbot v1.0\n\n"
                f"📡 **Telegram Library**\nTelethon\n\n"
                f"💾 **Baza yaxlitligi**\n{integrity}\n\n"
                f"⚙️ **Faol ishchilar**\n{workers}\n\n"
                f"⏱ **Ishlash vaqti**\n{uptime}s"
            ), "result")

        @self.command("stat", "Show system dashboard", "system")
        async def stat_command(event, parsed):
            snap = await self.system.snapshot()
            running = sum(1 for state in snap.workers.values() if getattr(state, "value", str(state)).lower() == "running")
            counts = await self.control.counts()
            bio = await self.profile.load("bio")
            status = await self.profile.load("status")
            body = (
                f"🖥 **TIZIM**\n⏱ Uptime: `{fmt_uptime(snap.uptime)}`\n"
                f"💾 Baza: {'🟢 Sog‘lom' if snap.database_ok else '🔴 Ogohlantirish'}\n"
                f"⚙️ Ishchilar: **{running}/{len(snap.workers)} faol**\n\n━━━━━━━━━━━━\n\n"
                "**FAOL FUNKSIYALAR**\n"
                f"📝 Avto Bio: {'🟢 Faol' if bio and bio.enabled else '⚪ O‘chiq'}\n"
                f"😊 Avto Status: {'🟢 Faol' if status and status.enabled else '⚪ O‘chiq'}\n"
                f"🔇 Mute qilinganlar: {counts['muted']}\n🚫 Bloklanganlar: {counts['blocked']}\n\n━━━━━━━━━━━━\n\n"
                f"**STATISTIKA**\n⌨️ Ro‘yxatdan o‘tgan buyruqlar: {snap.commands}\n"
                f"📈 Bajarilgan buyruqlar: {await self.system.command_count()}\n⚠️ Qayd qilingan xatolar: {snap.errors}"
            )
            await self.reply(event, UI.info("TIZIM PANELI", body) + UI.ready(self.owner_name), "result")

        @self.command("autoread", "Enable automatic read for private chats", "automation")
        async def autoread_command(event, parsed):
            mode = parsed.args[0].lower() if parsed.args else "start"
            if mode in {"status","info"}:
                state=await self.autoread.get("autoread")
                await self.reply(event, UI.info("AUTOREAD HOLATI",
                    f"📖 **Shaxsiy chatlar**\n{'🟢 Faol' if state['enabled'] else '⚪ O‘chiq'}\n\n"
                    "Guruhlar, kanallar va botlar bu rejimga kirmaydi."),"result"); return
            if mode=="help":
                await self.reply(event,UI.info("AUTOREAD YORDAMI","`.autoread`\n`.autoread status`\n`.autoread info`\n`.autoread test`"),"help"); return
            if mode=="test":
                await self.reply(event,UI.info("AUTOREAD TEST","Konfiguratsiya faol bo‘lsa, kelgan shaxsiy xabarlar event tizimi tomonidan o‘qilgan deb belgilanadi."),"result"); return
            await self.autoread.set("autoread",True,"private")
            await self.reply(event,UI.success("AUTOREAD YOQILDI",
                "📖 **Rejim**\nShaxsiy chatlar\n\n🚫 **Kiritilmaydi**\nGuruhlar • Kanallar • Botlar\n\nO‘qilgan deb belgilash faqat qo‘llab-quvvatlanadigan keluvchi xabarlarda bajariladi."
            )+UI.ready(self.owner_name),"result")

        @self.command("autoreadall", "Enable automatic read for supported chats", "automation")
        async def autoreadall_command(event, parsed):
            await self.autoread.set("autoreadall",True,"all_supported")
            await self.reply(event,UI.success("AUTOREAD ALL YOQILDI",
                "📖 **Shaxsiy chatlar**\nFaol\n\n👥 **Groups**\nTelegram o‘qilganini tasdiqlashga ruxsat berganda faol\n\n"
                "📢 **Channels**\nQo‘llab-quvvatlanganda faol\n\n🤖 **Botlar**\nFaol"
            )+UI.ready(self.owner_name),"result")

        @self.command("unread", "Disable autoread systems", "automation")
        async def unread_command(event, parsed):
            await self.autoread.set("autoread",False,None)
            await self.autoread.set("autoreadall",False,None)
            await self.reply(event,UI.info("AUTOREAD TIZIMLARI O‘CHIRILDI",
                "📖 **Autoread**\nO‘chiq\n\n📚 **Autoread All**\nO‘chiq\n\nBoshqa hech bir funksiya o‘zgartirilmadi."
            )+UI.ready(self.owner_name),"result")

        @self.command("taxrir", "Enable incoming message edit tracking", "tracking")
        async def taxrir_command(event, parsed):
            await self.autoread.set("edit_tracker",True,"incoming")
            await self.reply(event,UI.success("TAHRIR KUZATUVI YOQILDI",
                "✏️ **Qamrov**\nQo‘llab-quvvatlanadigan keluvchi xabarlar\n\n💾 **Tarix**\nSQLite doimiy saqlash tizimi\n\n"
                "Ikkala versiya mavjud bo‘lsa, asl va tahrirlangan matn saqlanadi."
            )+UI.ready(self.owner_name),"result")

        @self.command("untaxrir", "Disable edit tracking", "tracking")
        async def untaxrir_command(event, parsed):
            await self.autoread.set("edit_tracker",False,None)
            await self.reply(event,UI.info("TAHRIR KUZATUVI TO‘XTATILDI",
                "✏️ Kelajakdagi tahrirlar endi kuzatilmaydi.\n\n💾 Avvalgi tahrirlar tarixi saqlab qolindi."
            )+UI.ready(self.owner_name),"result")

        @self.command("log", "Connect a verified Telegram log destination", "control")
        async def log_command(event, parsed):
            if not parsed.args:
                await self.reply(event,UI.warning("LOG MANZILI KIRITILMADI",
                    "**NIMA BO‘LDI**\nKanal yoki chat ID kiritilishi kerak.\n\n**TAVSIYA**\nMasalan:\n`.log CHANNEL_ID`"),"result"); return
            target=parsed.args[0]
            try:
                entity,test=await self.logger.set_channel(target)
                title=getattr(entity,"title",None) or getattr(entity,"username",None) or str(target)
                await self.reply(event,UI.success("LOG KANALI ULANDI",
                    f"📢 **Kanal**\n{title}\n\n🆔 **ID**\n`{target}`\n\n📡 **Ulanish**\nTasdiqlandi\n\n📨 **Sinov xabari**\nYuborildi"
                )+UI.ready(self.owner_name),"persistent")
            except Exception as exc:
                await self.reply(event,UI.error("LOG KANALIGA ULANISH BAJARILMADI",
                    f"**SABABI**\n`{type(exc).__name__}: {str(exc)[:250]}`\n\n"
                    "**TAVSIYA**\nID, akkaunt ruxsati va xabar yuborish huquqini tekshiring."),"critical")





        def fmt_uptime(seconds):
            seconds=max(0,int(seconds))
            h,rem=divmod(seconds,3600); m,s=divmod(rem,60)
            return f"{h:02}:{m:02}:{s:02}"

        @self.command("calc","Safely calculate mathematical expressions","tools")
        async def calc_command(event,parsed):
            mode=parsed.args[0].lower() if parsed.args else None
            if mode=="help":
                await self.reply(event,UI.info("KALKULYATOR YORDAMI",
                    "`.calc 2+2`\n`.calc (50+20)*3`\n`.calc sqrt(144)`\n`.calc 2^10`\n`.calc 20%`\n\n"
                    "REJIMLAR:\n`.calc history`\n`.calc examples`\n\nFaqat cheklangan xavfsiz matematik parser ishlatiladi. Python `eval()` hech qachon ishlatilmaydi."
                ),"help"); return
            if mode=="examples":
                await self.reply(event,UI.info("KALKULYATOR MISOLLARI",
                    "`.calc 2+2`\n`.calc 50*20`\n`.calc (50+20)*3`\n`.calc sqrt(144)`\n`.calc 2^10`\n`.calc 20%`"
                ),"help"); return
            if mode=="history":
                history=getattr(self,"_calc_history",{}).get(event.chat_id,[])
                body="Hozircha hisoblashlar yo‘q." if not history else "\n".join(
                    f"`{x.expression}` = **{x.result}**" for x in history[-10:][::-1])
                await self.reply(event,UI.info("HISOBLASH TARIXI",body),"result"); return
            expression=" ".join(parsed.args)
            try:
                result=self.calculator.calculate(expression)
            except CalculatorError as exc:
                await self.reply(event,UI.warning("HISOBLASH BAJARILMADI",
                    f"**SABABI**\n{exc}\n\n**EXAMPLE**\n`.calc (50+20)*3`"),"result"); return
            if not hasattr(self,"_calc_history"): self._calc_history={}
            self._calc_history.setdefault(event.chat_id,[]).append(result)
            self._calc_history[event.chat_id]=self._calc_history[event.chat_id][-30:]
            await self.reply(event,UI.success("HISOBLASH NATIJASI",
                f"🧮 **Ifoda**\n`{result.expression}`\n\n📊 **Natija**\n**{result.result}**"
            ),"result")

        @self.command("del", "Akkaunt yuborgan so‘nggi xabarlarni o‘chirish", "tools")
        async def del_command(event, parsed):
            token = parsed.args[0].lower() if parsed.args else None
            if token == "help":
                await self.reply(event, UI.info("XABAR O‘CHIRISH YORDAMI", "`.del 1` — 1 ta xabar\n`.del 50` — 50 tagacha xabar\n`.del 30m` — oxirgi 30 daqiqa\n`.del 1h` — oxirgi 1 soat\n`.del today` — bugungi xabarlar\n\nQo‘shimcha: `.del status`, `.del cancel`, `.del examples`\n\nFaqat o‘zingiz yuborgan xabarlar ko‘rib chiqiladi."), "help"); return
            if token == "examples":
                await self.reply(event, UI.info("XABAR O‘CHIRISH MISOLLARI", "`.del 1`\n`.del 50`\n`.del 100`\n`.del 30m`\n`.del 1h`\n`.del today`"), "help"); return
            if token == "status":
                active = self.deleter.active(event.chat_id)
                await self.reply(event, UI.info("O‘CHIRISH HOLATI", "🟢 Hozir o‘chirish jarayoni ishlamoqda." if active else "⚪ Bu chatda faol o‘chirish jarayoni yo‘q."), "result"); return
            if token == "cancel":
                cancelled = self.deleter.cancel(event.chat_id)
                await self.reply(event, UI.info("O‘CHIRISHNI TO‘XTATISH", "🟡 To‘xtatish so‘rovi qabul qilindi." if cancelled else "Faol o‘chirish jarayoni topilmadi."), "result"); return
            if not token:
                await self.reply(event, UI.warning("O‘CHIRILADIGAN MIQDOR ANIQLANMADI", "**NIMA BO‘LDI**\nQancha xabarni qayta ishlash kerakligi aniqlanmadi.\n\n**TO‘G‘RI FORMAT**\n`.del 50`, `.del 1h` yoki `.del today`"), "result"); return
            limit = None; since = None
            try:
                if token.isdigit():
                    limit = int(token)
                    if not 1 <= limit <= 5000: raise ValueError("Miqdor 1 dan 5000 gacha bo‘lishi kerak.")
                else:
                    _, since = self.deleter.parse_period(token)
            except ValueError as exc:
                await self.reply(event, UI.warning("O‘CHIRISH SO‘ROVI NOTO‘G‘RI", f"**SABABI**\n{exc}\n\n**MISOL**\n`.del 50` yoki `.del 30m`"), "result"); return

            progress_msg = await self.reply(event, UI.loading("XABARLAR TOZALANMOQDA", "O‘zingiz yuborgan xabarlar tekshirilmoqda..."), "progress")
            progress_id = getattr(progress_msg, "id", None)
            if progress_id is None:
                progress_id = getattr(getattr(progress_msg, "message", None), "id", None)
            exclude_ids = {progress_id} if progress_id is not None else set()
            if progress_id is None:
                raise RuntimeError("Jarayon holati uchun Telegram xabari yaratilmagan.")
            async def progress(result, index, total):
                percent = int(index * 100 / total); filled = min(10, percent // 10); bar = "█" * filled + "░" * (10-filled)
                try:
                    await progress_msg.edit(UI.header("XABARLAR TOZALANMOQDA") + f"\n\n{bar} **{percent}%**\n\n📨 **Topildi**\n{result.found}\n\n🗑 **O‘chirildi**\n{result.deleted}\n\n⏭ **O‘tkazib yuborildi**\n{result.skipped}\n\n⚠️ **Xatolar**\n{result.errors}")
                except Exception as exc:
                    await self.db.log_error("delete_progress", exc)
            try:
                result = await self.deleter.delete_recent_own(event, limit=limit, since=since, progress=progress, exclude_ids=exclude_ids)
                status = "🟡 Jarayon xavfsiz to‘xtatildi" if result.cancelled else "🟢 Vazifa yakunlandi"
                await progress_msg.edit(UI.header("XABARLARNI TOZALASH NATIJASI") + f"\n\n{status}\n\n🔎 **Tekshirildi**\n{result.scanned}\n\n📨 **Topildi**\n{result.found}\n\n🗑 **O‘chirildi**\n{result.deleted}\n\n⏭ **O‘tkazib yuborildi**\n{result.skipped}\n\n⚠️ **Xatolar**\n{result.errors}" + UI.ready(self.owner_name))
                await self.cleanup.finalize(event.chat_id, progress_id, "result")
            except Exception as exc:
                await self.db.log_error("delete", exc)
                try:
                    await progress_msg.edit(UI.error("XABARLARNI O‘CHIRISH BAJARILMADI", f"**NIMA BO‘LDI**\nJarayon yakunlanmadi.\n\n**SABABI**\n`{type(exc).__name__}: {str(exc)[:300]}`\n\n**HOLAT**\nTasdiqlanmagan o‘chirish muvaffaqiyati ko‘rsatilmaydi."))
                    await self.cleanup.finalize(event.chat_id, progress_id, "result")
                except Exception:
                    pass

        def parse_rotation(raw_args):
            text=" ".join(raw_args).strip()
            if not text:
                raise ValueError("Qiymatlar kiritilmadi.")
            interval=60
            if " : " in text:
                text, tail=text.rsplit(" : ",1)
                if not tail.strip().isdigit(): raise ValueError("Interval musbat soniyalarda berilishi kerak.")
                interval=int(tail.strip())
            elif ":" in text and text.rsplit(":",1)[1].strip().isdigit():
                text,tail=text.rsplit(":",1); interval=int(tail.strip())
            if interval<30: raise ValueError("Eng kichik interval 30 soniya.")
            mode="random"
            lower=text.lower().strip()
            if lower.endswith(" random"):
                text=text[:-7].strip(); mode="random"
            elif lower.endswith(" sequence"):
                text=text[:-9].strip(); mode="sequence"
            values=[x.strip() for x in text.split("|") if x.strip()]
            if not values: raise ValueError("Yaroqli qiymatlar topilmadi.")
            if len(set(values))!=len(values): raise ValueError("Bir xil qiymatlarni takrorlash mumkin emas.")
            return values,mode,interval

        @self.command("bio","Configure automatic Telegram bio rotation","profile")
        async def bio_command(event,parsed):
            mode=parsed.args[0].lower() if parsed.args else None
            if mode in {"status","current","original"}:
                state=await self.profile.load("bio")
                current=await self.profile.current_bio()
                if mode=="current":
                    await self.reply(event,UI.info("JORIY BIO",current or "Hozircha bio o‘rnatilmagan."),"result");return
                if mode=="original":
                    await self.reply(event,UI.info("ASL BIO",(state.previous if state and state.previous is not None else "Zaxira nusxa mavjud emas.")),"result");return
                body="⚪ O‘chiq"
                if state: body=f"{'🟢 Faol' if state.enabled else '⚪ O‘chiq'}\n\n🔄 Rejim: {state.mode}\n⏱ Interval: {state.interval} soniya\n📝 Variantlar: {len(state.values)}"
                await self.reply(event,UI.info("BIO TIZIMI HOLATI",body),"result");return
            if mode=="help":
                await self.reply(event,UI.info("BIO YORDAMI","`.bio Hello`\n`.bio Hello | World`\n`.bio Hello | World : 60`\n"
                    "`.bio Hello | World random : 60`\n`.bio Hello | World sequence : 60`\n\nModes:\n`.bio status`\n`.bio current`\n`.bio original`\n`.bio examples`"),"help");return
            if mode=="examples":
                await self.reply(event,UI.info("BIO MISOLLARI","`.bio Hello`\n`.bio Online | Working : 60`\n`.bio One | Two sequence : 45`"),"help");return
            try: values,rotation,interval=parse_rotation(parsed.args)
            except ValueError as exc:
                await self.reply(event,UI.warning("BIO SOZLAMASI NOTO‘G‘RI",f"**SABABI**\n{exc}\n\n**EXAMPLE**\n`.bio Hello | World sequence : 60`"),"result");return
            previous=await self.profile.current_bio()
            state=RotationState(True,values,rotation,interval,previous)
            try:
                # Confirm the first update immediately rather than claiming activation only.
                first=self.profile.next_value(state)
                await self.profile.set_bio(first)
                await self.profile.save("bio",state)
                worker=self.workers.status("bio_worker")
                if not worker or worker.state != WorkerState.RUNNING:
                    await self.workers.start("bio_worker",self.profile.bio_worker)
                await self.logger.event("BIO O‘ZGARISHI",f"Mode: {rotation}\nInterval: {interval}s\nEntries: {len(values)}")
                await self.reply(event,UI.success("BIO TIZIMI YOQILDI",
                    f"📝 **Entries**\n{len(values)}\n\n🔄 **Mode**\n{rotation.title()}\n\n⏱ **Interval**\n{interval} seconds\n\n"
                    f"✅ **First Bio**\n{first}"
                )+UI.ready(self.owner_name),"result")
            except Exception as exc:
                await self.reply(event,UI.error("BIO YANGILANMADI",f"**SABABI**\n`{type(exc).__name__}: {str(exc)[:250]}`\n\nNo activation success was claimed."),"critical")

        @self.command("unbio","Stop automatic bio rotation","profile")
        async def unbio_command(event,parsed):
            state=await self.profile.stop("bio")
            if not state:
                await self.reply(event,UI.info("BIO TIZIMI ALLAQACHON O‘CHIQ","Saqlangan avtomatik bio sozlamasi topilmadi."),"result");return
            restored=False; restore_error=None
            if state.previous is not None:
                try: await self.profile.set_bio(state.previous); restored=True
                except Exception as exc: restore_error=type(exc).__name__
            body="🛑 **Almashtirish**\nTo‘xtatildi"
            body += "\n\n♻️ **Oldingi bio**\nTiklandi" if restored else "\n\n⚠️ **Oldingi bio**\nTiklanmadi"
            if restore_error: body+=f"\nSabab: `{restore_error}`"
            await self.reply(event,UI.info("BIO TIZIMI TO‘XTATILDI",body)+UI.ready(self.owner_name),"result")

        @self.command("autostatus","Avtomatik emoji statusini sozlash","profile")
        async def autostatus_command(event,parsed):
            mode=parsed.args[0].lower() if parsed.args else None
            if mode in {"status","current","info"}:
                state=await self.profile.load("status")
                body="⚪ O‘chiq" if not state else (
                    f"{'🟢 Faol' if state.enabled else '⚪ O‘chiq'}\n\n"
                    f"🔄 **Rejim**\n{'Ketma-ket' if state.mode == 'sequence' else 'Tasodifiy'}\n\n"
                    f"⏱ **Interval**\n{state.interval} soniya\n\n😊 **Emoji soni**\n{len(state.values)}"
                )
                await self.reply(event,UI.info("AVTO STATUS HOLATI",body),"result");return
            if mode=="help":
                await self.reply(event,UI.info("AVTO STATUS YORDAMI",
                    "`.autostatus EMOJI_ID`\n`.autostatus ID1 ID2 ID3`\n"
                    "`.autostatus ID1 ID2 sequence : 60`\n\n"
                    "REJIMLAR:\n`.autostatus status`\n`.autostatus current`\n`.autostatus examples`\n\n"
                    "Hozirgi build custom emoji IDlarini saqlaydi, lekin Telegram API orqali statusni real yangilash yo‘li tasdiqlanmaguncha soxta muvaffaqiyat ko‘rsatmaydi."),"help");return
            if mode=="examples":
                await self.reply(event,UI.info("AVTO STATUS MISOLLARI","`.autostatus 5276098269204754305`\n`.autostatus 111 222 sequence : 60`"),"help");return

            raw=" ".join(parsed.args).strip()
            if not raw:
                await self.reply(event,UI.warning("STATUS SOZLAMASI KIRITILMADI","Kamida bitta raqamli custom emoji ID kiriting.\n\n**MISOL**\n`.autostatus 5276098269204754305`"),"result");return
            interval=60
            if ":" in raw:
                left, tail=raw.rsplit(":",1)
                if not tail.strip().isdigit():
                    await self.reply(event,UI.warning("STATUS INTERVALI NOTO‘G‘RI","Interval musbat soniya ko‘rinishida bo‘lishi kerak.\n\n**MISOL**\n`.autostatus 111 222 : 60`"),"result");return
                raw=left.strip(); interval=int(tail.strip())
            if interval < 30:
                await self.reply(event,UI.warning("STATUS INTERVALI JUDA KICHIK","FloodWait xavfini kamaytirish uchun eng kichik interval 30 soniya.\n\n**MISOL**\n`.autostatus 111 222 : 30`"),"result");return
            words=raw.split()
            rotation="random"
            if words and words[-1].lower() in {"random","sequence"}:
                rotation=words.pop().lower()
            values=words
            if not values or any(not x.isdigit() or len(x)>20 for x in values):
                await self.reply(event,UI.warning("STATUS SOZLAMASI NOTO‘G‘RI","Faqat raqamli custom emoji IDlari qabul qilinadi.\n\n**MISOL**\n`.autostatus 111 222 sequence : 60`"),"result");return
            values=list(dict.fromkeys(values))
            state=RotationState(True,values,rotation,interval,None)
            # First update is attempted synchronously. We only start a repeating worker
            # after Telegram confirms the API request.
            first = self.profile.next_value(state)
            ok, api_error = await self.profile.set_status(first)
            if not ok:
                state.enabled=False
                await self.profile.save("status",state)
                await self.reply(event,UI.warning("AVTO STATUS FAOLLASHTIRILMADI",
                    f"😊 **Tekshirilgan emoji IDlari**\n{len(values)}\n\n"
                    "Telegram emoji status so‘rovi tasdiqlanmadi. Sozlama faol deb belgilanmadi va soxta muvaffaqiyat ko‘rsatilmaydi.\n\n"
                    f"**SABAB**\n{api_error or 'API mosligi tasdiqlanmadi'}"
                )+UI.ready(self.owner_name),"result"); return
            await self.profile.save("status",state)
            worker=self.workers.status("status_worker")
            if not worker or worker.state != WorkerState.RUNNING:
                await self.workers.start("status_worker",self.profile.status_worker)
            await self.reply(event,UI.success("AVTO STATUS FAOLLASHTIRILDI",
                f"😊 **Emoji IDlari**\n{len(values)}\n\n🔄 **Rejim**\n{'Ketma-ket' if rotation == 'sequence' else 'Tasodifiy'}\n\n⏱ **Interval**\n{interval} soniya\n\n"
                "Telegram API birinchi emoji status o‘zgarishini tasdiqladi."
            )+UI.ready(self.owner_name),"result")

        @self.command("unstatus","Stop automatic emoji status","profile")
        async def unstatus_command(event,parsed):
            state=await self.profile.stop("status")
            if not state:
                await self.reply(event,UI.info("AVTO STATUS ALLAQACHON O‘CHIQLI","Saqlangan avto status sozlamasi topilmadi."),"result");return
            await self.reply(event,UI.info("AVTO STATUS TO‘XTATILDI","Ishchi sozlamasi o‘chirildi. Status API mosligi hali tasdiqlanmagani uchun tiklandi deb soxta xabar ko‘rsatilmaydi.")+UI.ready(self.owner_name),"result")

        async def resolve_control_target(event, parsed, start=0):
            explicit=parsed.args[start] if len(parsed.args)>start else None
            try:
                return await self.targets.resolve(event,explicit)
            except TargetNotFound:
                await self.reply(event,UI.warning("FOYDALANUVCHI ANIQLANMADI",
                    "Kim nazarda tutilganini aniqlab bo‘lmadi.\n\n"
                    "**MAVJUD USULLAR**\n"
                    "👤 Username: `.mute @username`\n"
                    "🆔 ID: `.mute 123456789`\n"
                    "💬 Reply to a user, then use the command\n"
                    "📱 Use the command inside a private chat"
                )+UI.ready(self.owner_name),"result")
                return None

        @self.command("mute","Add a user to local mute policy","control")
        async def mute_command(event,parsed):
            mode=parsed.args[0].lower() if parsed.args else None
            if mode=="help":
                await self.reply(event,UI.info("MUTE YORDAMI",
                    "`.mute @username`\n`.mute 123456789`\nReply + `.mute`\nPrivate chat + `.mute`\n\n"
                    "REJIMLAR:\n`.mute status`\n`.mute list`\n`.mute info @username`\n`.mute check @username`"),"help"); return
            if mode=="status":
                c=await self.control.counts()
                await self.reply(event,UI.info("MUTE HOLATI",f"🔇 **Faol mahalliy mute qilinganlar**\n{c['muted']}\n\n"
                    "Bu funksiya mahalliy userbot qoidasini saqlaydi; Telegram shaxsiy akkauntlari uchun yagona server tomondagi mute-user API mavjud emas."),"result"); return
            if mode=="list":
                rows=await self.control.mute_list()
                body="Faol mute qilingan foydalanuvchilar yo‘q." if not rows else "\n\n".join(
                    f"{i}. **@{u}**" if u else f"{i}. **{d}**\n   🆔 `{uid}`" for i,(uid,u,d) in enumerate(rows[:30],1))
                await self.reply(event,UI.info("MUTE QILINGANLAR",body),"result"); return
            if mode in {"info","check"}:
                target=await resolve_control_target(event,parsed,1)
                if not target:return
                row=await self.control.muted(target.user_id)
                active=bool(row and row[3])
                await self.reply(event,UI.info("MUTE TEKSHIRUVI",
                    f"👤 **Foydalanuvchi**\n{target.display_name}\n\n🔇 **Local policy**\n{'🟢 Mute qilingan' if active else '⚪ Mute qilinmagan'}"),"result"); return
            target=await resolve_control_target(event,parsed)
            if not target:return
            await self.control.mute(target)
            await self.logger.event("MUTE",f"User: {target.display_name}\nID: `{target.user_id}`")
            await self.reply(event,UI.success("MAHALLIY MUTE YOQILDI",
                f"👤 **Foydalanuvchi**\n{target.display_name}\n\n🆔 **ID**\n`{target.user_id}`\n\n"
                "🔇 **Holat**\nFaol mahalliy userbot mute qoidasi\n\n"
                "Telegram shaxsiy akkauntlar uchun universal serverdagi foydalanuvchini mute qilish API sini bermaydi. Shu sabab masofaviy akkaunt holati o‘zgardi deb ko‘rsatilmaydi."
            )+UI.ready(self.owner_name),"result")

        @self.command("unmute","Remove a user from local mute policy","control")
        async def unmute_command(event,parsed):
            if parsed.args and parsed.args[0].lower()=="help":
                await self.reply(event,UI.info("UNMUTE YORDAMI","`.unmute @username`\nReply + `.unmute`\nPrivate chat + `.unmute`"),"help");return
            if parsed.args and parsed.args[0].lower()=="status":
                c=await self.control.counts()
                await self.reply(event,UI.info("UNMUTE HOLATI",f"🔇 Faol mahalliy mute qilinganlar: {c['muted']}"),"result");return
            target=await resolve_control_target(event,parsed)
            if not target:return
            changed=await self.control.unmute(target)
            if not changed:
                await self.reply(event,UI.info("FOYDALANUVCHI MUTE QILINMAGAN",f"**{target.display_name}** uchun faol mahalliy mute qoidasi yo‘q."),"result");return
            await self.logger.event("UNMUTE",f"User: {target.display_name}\nID: `{target.user_id}`")
            await self.reply(event,UI.success("MAHALLIY MUTE O‘CHIRILDI",f"👤 **Foydalanuvchi**\n{target.display_name}\n\n🔊 Mahalliy qoida o‘chirildi.")+UI.ready(self.owner_name),"result")

        @self.command("block","Block a Telegram user","control")
        async def block_command(event,parsed):
            mode=parsed.args[0].lower() if parsed.args else None
            if mode=="help":
                await self.reply(event,UI.info("BLOCK YORDAMI","`.block @username`\n`.block 123456789`\nReply + `.block`\nPrivate chat + `.block`\n\n"
                    "REJIMLAR:\n`.block status`\n`.block list`\n`.block info @username`\n`.block check @username`"),"help");return
            if mode=="status":
                c=await self.control.counts()
                await self.reply(event,UI.info("BLOKLASH HOLATI",f"🚫 **Faol bloklangan foydalanuvchilar**\n{c['blocked']}"),"result");return
            if mode=="list":
                rows=await self.control.block_list()
                body="Faol bloklangan foydalanuvchilar yo‘q." if not rows else "\n\n".join(
                    f"{i}. **@{u}**" if u else f"{i}. **{d}**\n   🆔 `{uid}`" for i,(uid,u,d) in enumerate(rows[:30],1))
                await self.reply(event,UI.info("BLOKLANGANLAR RO‘YXATI",body),"result");return
            if mode in {"info","check"}:
                target=await resolve_control_target(event,parsed,1)
                if not target:return
                row=await self.control.blocked(target.user_id)
                active=bool(row and row[3])
                await self.reply(event,UI.info("BLOKLASH TEKSHIRUVI",f"👤 **Foydalanuvchi**\n{target.display_name}\n\n🚫 **Holat**\n{'🟢 Bloklangan' if active else '⚪ Bloklanmagan'}"),"result");return
            target=await resolve_control_target(event,parsed)
            if not target:return
            try:
                await self.control.block(target)
                await self.logger.event("BLOCK",f"User: {target.display_name}\nID: `{target.user_id}`")
                await self.reply(event,UI.success("FOYDALANUVCHI BLOKLANDI",
                    f"👤 **Foydalanuvchi**\n{target.display_name}\n\n🆔 **ID**\n`{target.user_id}`\n\n🚫 **Telegram amali**\nTasdiqlandi"
                )+UI.ready(self.owner_name),"result")
            except Exception as exc:
                await self.logger.error("BLOCK", exc)
                await self.reply(event,UI.error("BLOKLASH BAJARILMADI",
                    f"**SABABI**\n`{type(exc).__name__}: {str(exc)[:250]}`\n\nMuvaffaqiyat qayd qilinmadi."),"critical")

        @self.command("unblock","Unblock a Telegram user","control")
        async def unblock_command(event,parsed):
            if parsed.args and parsed.args[0].lower()=="help":
                await self.reply(event,UI.info("UNBLOCK YORDAMI","`.unblock @username`\nReply + `.unblock`\nPrivate chat + `.unblock`"),"help");return
            if parsed.args and parsed.args[0].lower()=="status":
                c=await self.control.counts()
                await self.reply(event,UI.info("UNBLOKLASH HOLATI",f"🚫 Faol bloklangan foydalanuvchilar: {c['blocked']}"),"result");return
            target=await resolve_control_target(event,parsed)
            if not target:return
            try:
                await self.control.unblock(target)
                await self.logger.event("UNBLOCK",f"User: {target.display_name}\nID: `{target.user_id}`")
                await self.reply(event,UI.success("FOYDALANUVCHI BLOKDAN CHIQARILDI",
                    f"👤 **Foydalanuvchi**\n{target.display_name}\n\n🔓 **Telegram amali**\nTasdiqlandi"
                )+UI.ready(self.owner_name),"result")
            except Exception as exc:
                await self.logger.error("UNBLOCK", exc)
                await self.reply(event,UI.error("BLOKDAN CHIQARISH BAJARILMADI",
                    f"**SABABI**\n`{type(exc).__name__}: {str(exc)[:250]}`\n\nMuvaffaqiyat qayd qilinmadi."),"critical")

        @self.command("story", "Foydalanuvchi Story kuzatuvi va holatini boshqarish", "tracking")
        async def story_command(event, parsed):
            mode = parsed.args[0].lower() if parsed.args else None
            modes = {"status", "list", "info", "check", "help", "examples"}

            if mode == "help":
                await self.reply(event, UI.info(
                    "STORY YORDAMI",
                    "`.story @username` — foydalanuvchini kuzatuv ro‘yxatiga qo‘shish\n"
                    "`.story 123456789` — ID orqali qo‘shish\n"
                    "Xabarga javob + `.story` — xabar egasini tanlash\n"
                    "Shaxsiy chat + `.story` — hozirgi suhbatdoshni tanlash\n\n"
                    "REJIMLAR:\n`.story status`\n`.story list`\n"
                    "`.story info @username`\n`.story check @username`"
                ), "help")
                return

            if mode == "examples":
                await self.reply(event, UI.info(
                    "STORY MISOLLARI",
                    "`.story @username`\n`.story 123456789`\n"
                    "`.story status`\n`.story list`\n"
                    "`.story check @username`"
                ), "help")
                return

            if mode == "status":
                data = await self.story.stats()
                worker = self.workers.status("story_worker")
                state = "🟢 Faol" if worker and worker.state == WorkerState.RUNNING else "⚪ Kutilmoqda"
                await self.reply(event, UI.info(
                    "STORY TIZIMI HOLATI",
                    f"👥 **Faol kuzatuvlar**\n{data['active']}\n\n"
                    f"😊 **Tasdiqlangan reaksiyalar**\n{data['reactions']}\n\n"
                    f"⚠️ **Xatolar**\n{data['errors']}\n\n"
                    f"⚙️ **Ishchi**\n{state}"
                ), "result")
                return

            if mode == "list":
                targets = await self.story.list_targets()
                if not targets:
                    await self.reply(event, UI.info(
                        "STORY KUZATUV RO‘YXATI",
                        "Hozircha faol kuzatuvchilar yo‘q.\n\nQo‘shish uchun:\n`.story @username`"
                    ), "result")
                    return
                lines = []
                for i, target in enumerate(targets[:20], 1):
                    name = f"@{target.username}" if target.username else target.display_name
                    reaction = target.reaction or "Standart"
                    lines.append(f"{i}. **{name}**\n   😊 {reaction}\n   🟢 Faol")
                await self.reply(event, UI.info(
                    "STORY KUZATUV RO‘YXATI",
                    "\n\n".join(lines)
                ), "result")
                return

            if mode in {"info", "check"}:
                explicit = parsed.args[1] if len(parsed.args) > 1 else None
                try:
                    target = await self.targets.resolve(event, explicit)
                except TargetNotFound:
                    await self.reply(event, UI.warning(
                        "FOYDALANUVCHI ANIQLANMADI",
                        "`.story info @username` yozing yoki foydalanuvchi xabariga javob berib buyruq yuboring."
                    ), "result")
                    return

                if mode == "info":
                    saved = await self.story.get_target(target.user_id)
                    if not saved:
                        await self.reply(event, UI.info(
                            "STORY KUZATUV MA’LUMOTI",
                            f"👤 **Foydalanuvchi**\n{target.display_name}\n\n"
                            "⚪ Kuzatuv faol emas."
                        ), "result")
                        return
                    name = f"@{saved.username}" if saved.username else saved.display_name
                    await self.reply(event, UI.info(
                        "STORY KUZATUV MA’LUMOTI",
                        f"👤 **Foydalanuvchi**\n{name}\n\n🆔 **ID**\n`{saved.user_id}`\n\n"
                        f"📡 **Kuzatuv**\n{'Faol' if saved.active else 'To‘xtatilgan'}\n\n"
                        f"😊 **Reaksiya**\n{saved.reaction or 'Standart'}"
                    ), "result")
                    return

                result = await self.story.check_target(target)
                if not result["supported"]:
                    await self.reply(event, UI.warning(
                        "STORY TEKSHIRILDI, LEKIN API CHEKLOVI BOR",
                        f"👤 **Foydalanuvchi**\n{target.display_name}\n\n"
                        "📡 **Tekshiruv holati**\nFoydalanuvchi tekshirildi deb qayd etildi\n\n"
                        "⚠️ **API mosligi**\n" + result["reason"] +
                        "\n\nHech qanday tasdiqlanmagan reaksiya yuborildi deb ko‘rsatilmaydi."
                    ), "result")
                    return
                await self.reply(event, UI.info(
                    "STORY TEKSHIRUVI",
                    f"👤 **Foydalanuvchi**\n{target.display_name}\n\n"
                    f"📖 **Topilgan Storylar**\n{result.get('stories_found', 'Aniqlanmadi')}\n\n"
                    f"😊 **Tasdiqlangan reaksiyalar**\n{result.get('reacted', 0)}"
                ), "result")
                return

            # Standart: target + optional custom emoji ID
            explicit = parsed.args[0] if parsed.args else None
            reaction = parsed.args[1] if len(parsed.args) > 1 else None
            try:
                target = await self.targets.resolve(event, explicit)
            except TargetNotFound:
                await self.reply(event, UI.warning(
                    "FOYDALANUVCHI ANIQLANMADI",
                    "Kimni kuzatmoqchi ekaningizni aniqlab bo‘lmadi.\n\n"
                    "**MAVJUD USULLAR**\n"
                    "👤 `.story @username`\n"
                    "🆔 `.story 123456789`\n"
                    "💬 Foydalanuvchi xabariga javob berib `.story` yuboring\n"
                    "📱 Shaxsiy chat ichida `.story` yuboring"
                ) + UI.ready(self.owner_name), "result")
                return

            if reaction and not reaction.isdigit():
                await self.reply(event, UI.warning(
                    "MAXSUS EMOJI ID NOTO‘G‘RI",
                    "Kiritilgan custom emoji ID faqat raqamlardan iborat bo‘lishi kerak.\n\n"
                    "Misol:\n`.story @username 5276098269204754305`"
                ), "result")
                return

            created = await self.story.add_target(target, reaction)
            check = await self.story.check_target(target)
            # Ishchi faqat haqiqiy Story API yo‘li tasdiqlanganda ishga tushadi.
            if check["supported"]:
                worker = self.workers.status("story_worker")
                if not worker or worker.state != WorkerState.RUNNING:
                    story_worker = StoryWorker(self.story)
                    await self.workers.start("story_worker", story_worker.run)
            name = f"@{target.username}" if target.username else target.display_name
            title = "STORY MA’LUMOTI SAQLANDI" if created else "STORY MA’LUMOTI YANGILANDI"
            api_note = (
                "📖 **Mavjud Storylar**\nJoriy build imkoniyati doirasida tekshirildi"
                if check["supported"] else
                "⚠️ **Story API**\nKuzatuvchi saqlandi, ammo API mosligi tasdiqlanmaguncha reaksiya yuborish o‘chirilgan."
            )
            body = (
                f"👤 **Foydalanuvchi**\n{name}\n\n"
                f"🆔 **ID**\n`{target.user_id}`\n\n"
                + ("📡 **Kuzatuv holati**\nFaol" if check["supported"] else "⚠️ **Kuzatuv holati**\nAPI mosligi tasdiqlanishini kutmoqda")
                + "\n\n"
                + f"😊 **Reaksiya**\n{reaction or 'Qo‘llab-quvvatlansa, sozlangan standart reaksiya'}\n\n"
                + api_note
                + "\n\n**KEYINGI AMALLAR**\n"
                + "• `.story status`\n• `.story list`\n"
                + f"• `.unstory {target.user_id}`"
            )
            await self.reply(event, UI.success(title, body) + UI.ready(self.owner_name), "result")

        @self.command("unstory", "Foydalanuvchi Story kuzatuvini to‘xtatish", "tracking")
        async def unstory_command(event, parsed):
            mode = parsed.args[0].lower() if parsed.args else None
            if mode == "status":
                data = await self.story.stats()
                await self.reply(event, UI.info(
                    "STORY KUZATUVI HOLATI",
                    f"👥 Faol kuzatuvchilar: {data['active']}"
                ), "result")
                return
            if mode == "help":
                await self.reply(event, UI.info(
                    "UNSTORY YORDAMI",
                    "`.unstory @username`\n`.unstory 123456789`\n"
                    "Xabarga javob + `.unstory`\nShaxsiy chat + `.unstory`"
                ), "help")
                return
            try:
                explicit = parsed.args[0] if parsed.args else None
                target = await self.targets.resolve(event, explicit)
            except TargetNotFound:
                await self.reply(event, UI.warning(
                    "FOYDALANUVCHI ANIQLANMADI",
                    "Foydalanuvchini ko‘rsating, uning xabariga javob bering yoki buyruqni shaxsiy chatda ishlating."
                ), "result")
                return
            removed = await self.story.remove_target(target.user_id)
            if not removed:
                await self.reply(event, UI.info(
                    "STORY KUZATUVI FAOL EMAS",
                    f"{target.display_name} uchun faol kuzatuv topilmadi."
                ), "result")
                return
            await self.reply(event, UI.success(
                "STORY KUZATUVI TO‘XTATILDI",
                f"👤 **Foydalanuvchi**\n{target.display_name}\n\n"
                "Kelajakdagi kuzatuv o‘chirildi. Avvalgi amallar tarixi saqlanadi."
            ) + UI.ready(self.owner_name), "result")


    async def start(self):
        await self.db.connect()
        if await self.db.integrity_check() != "ok":
            raise RuntimeError("SQLite yaxlitlik tekshiruvi muvaffaqiyatsiz tugadi.")

        self.response_history = ResponseHistoryService(self.db)
        self.story = StoryService(self.db, self.client)
        await self.story.initialize()
        self.autoread = AutoreadService(self.db)
        await self.autoread.initialize()
        self.edits = EditService(self.db)
        await self.edits.initialize()
        self.logger = LoggerService(self.db, self.client)
        await self.logger.initialize()
        self.control = ControlService(self.db, self.client)
        await self.control.initialize()
        self.profile = ProfileService(self.db, self.client)
        await self.profile.initialize()
        self.deleter = DeleteService(self.client)
        self.system = SystemService(self.db, self.workers, self.registry, self.started_at)
        self.cleanup = ResponseCleanup(self.client, self.response_history, limit=2)
        # Qayta ishga tushgandan keyin saqlangan aylanish ishchilarini tiklash.
        for feature, worker_name, runner in (("bio", "bio_worker", self.profile.bio_worker), ("status", "status_worker", self.profile.status_worker)):
            state = await self.profile.load(feature)
            if state and state.enabled:
                await self.workers.start(worker_name, runner)
        self.register_commands()
        self.registry.validate()
        allowed = {"on","off","story","unstory","autoread","autoreadall","unread",
                   "taxrir","untaxrir","mute","unmute","log","help","stat","info",
                   "ping","calc","autostatus","unstatus","bio","unbio","del","block","unblock"}
        actual = set(self.registry.names())
        unexpected = actual - allowed
        missing = allowed - actual
        if unexpected or missing:
            raise RuntimeError(f"Public command audit failed. Unexpected={sorted(unexpected)} Missing={sorted(missing)}")
        typo = TypoEngine(self.registry.names())

        @self.client.on(events.NewMessage(incoming=True))
        async def incoming_message(event):
            # Cache originals for later edit comparison.
            self.original_messages[(event.chat_id,event.id)] = {
                "text": event.raw_text or "", "date": event.date,
                "sender_id": event.sender_id
            }
            # Uzoq ishlashda xabar keshi cheksiz o‘sib ketmasligi uchun limit.
            if len(self.original_messages) > 5000:
                oldest = next(iter(self.original_messages))
                self.original_messages.pop(oldest, None)
            all_state = await self.autoread.get("autoreadall")
            private_state = await self.autoread.get("autoread")
            should_read = False
            if all_state["enabled"]:
                should_read = True
            elif private_state["enabled"] and event.is_private:
                # `.autoread` shaxsiy chatlar uchun, ammo bot chatlari bundan mustasno.
                try:
                    sender = await event.get_sender()
                    should_read = not bool(getattr(sender, "bot", False))
                except Exception:
                    should_read = False
            if should_read:
                try:
                    await self.client.send_read_acknowledge(event.chat_id, max_id=event.id)
                except Exception as exc:
                    try:
                        await self.db.log_error("autoread", f"{type(exc).__name__}: {str(exc)[:300]}")
                    except Exception:
                        pass

        @self.client.on(events.MessageEdited(incoming=True))
        async def edited_message(event):
            state=await self.autoread.get("edit_tracker")
            if not state["enabled"]:
                return
            key=(event.chat_id,event.id)
            old=self.original_messages.get(key)
            if not old:
                return
            new=event.raw_text or ""
            original=old["text"]
            if new==original:
                return
            try:
                sender=await event.get_sender()
                username=getattr(sender,"username",None)
                count=await self.edits.record(
                    event.chat_id,event.id,event.sender_id,username,original,new,
                    old["date"].isoformat() if old["date"] else None,
                    event.date.isoformat() if event.date else None
                )
                self.original_messages[key]["text"]=new
                await self.logger.event("MESSAGE EDITED",
                    f"Chat: `{event.chat_id}`\nUser: {username or event.sender_id}\nEdit count: {count}\n\nOriginal:\n{original[:1000]}\n\nEdited:\n{new[:1000]}"
                )
            except Exception as exc:
                try:
                    await self.db.log_error("edit_tracker", f"{type(exc).__name__}: {str(exc)[:300]}")
                except Exception:
                    pass

        @self.client.on(events.NewMessage(outgoing=True))
        async def handler(event):
            parsed = parse_command(event.raw_text, self.settings.command_prefix)
            if not parsed:
                return

            command = self.registry.get(parsed.name)
            if not command:
                suggestion = typo.suggest(parsed.name)
                body = f"Siz kiritdingiz:\n`.{parsed.name}`\n\n"
                body += f"Balki shuni nazarda tutgandirsiz:\n`.{suggestion}`" if suggestion else "Mavjud buyruqlarni ko‘rish uchun `.help` yozing."
                await self.reply(event, UI.warning("BUYRUQ TOPILMADI", body), "result")
                return

            try:
                await self.db.increment_command(command.name)
                await command.handler(event, parsed)
            except Exception as exc:
                try:
                    await self.db.log_error(
                        f"command:{command.name}",
                        f"{type(exc).__name__}: {str(exc)[:500]}",
                    )
                except Exception:
                    pass
                await self.reply(event, UI.error(
                    "BUYRUQ BAJARILMADI",
                    f"**NIMA BO‘LDI**\nAmal kutilmagan sabab bilan yakunlanmadi.\n\n"
                    f"**SABABI**\n`{type(exc).__name__}`\n\n"
                    f"**TAFSILOT**\n`{str(exc)[:350] or 'Xatolik tafsiloti mavjud emas.'}`\n\n"
                    "**TAVSIYA**\nKiritilgan ma’lumot, Telegram ruxsatlari va ulanishni tekshirib, qayta urinib ko‘ring."
                ), "critical")

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))
            except (NotImplementedError, RuntimeError):
                pass

        await self.client.start()
        me = await self.client.get_me()
        self.owner_name = self._derive_owner_name(me, self.settings.owner_name)
        print(f"USERBOT ISHGA TUSHDI: {getattr(me, 'id', 'noma’lum')}")
        print(f"Hammasi tayyor, {self.owner_name}.")
        await self.client.run_until_disconnected()

    async def shutdown(self):
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        try:
            await self.workers.stop_all()
        finally:
            try:
                await self.db.close()
            finally:
                if self.client.is_connected():
                    await self.client.disconnect()


async def main():
    app = App()
    try:
        await app.start()
    finally:
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
