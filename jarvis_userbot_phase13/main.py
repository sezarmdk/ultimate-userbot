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
        @self.command("help", "Show command categories", "control")
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
            await self.reply(event, UI.info("USERBOT CONTROL", body) + UI.ready(self.settings.owner_name), "help")

        @self.command("on", "Start real online connection worker", "system")
        async def on_command(event, parsed):
            mode = parsed.args[0].lower() if parsed.args else "start"
            info = self.workers.status("online_worker")

            if mode in {"status", "info"}:
                state = info.state.value if info else "stopped"
                started = info.started_at.isoformat() if info and info.started_at else "—"
                await self.reply(event, UI.info(
                    "ONLINE SYSTEM STATUS",
                    f"📡 **State**\n{state.title()}\n\n⏱ **Started**\n{started}\n\n"
                    "ℹ️ This reports the real connection worker state, not a fake permanent online guarantee."
                ), "result")
                return

            if mode == "help":
                await self.reply(event, UI.info(
                    "ONLINE SYSTEM HELP",
                    "`.on` — start worker\n`.on status` — check state\n`.off` — stop only this worker"
                ), "help")
                return

            worker = OnlineWorker(self.client)
            info, started = await self.workers.start("online_worker", worker.run)
            if not started:
                await self.reply(event, UI.info(
                    "ONLINE SYSTEM ALREADY ACTIVE",
                    f"📡 **State**\nActive\n\n🔄 **Worker**\nHealthy"
                ) + UI.ready(self.settings.owner_name), "result")
                return

            await self.reply(event, UI.success(
                "ONLINE CONNECTION SYSTEM ACTIVE",
                "📡 **Connection Worker**\nRunning\n\n"
                "🔄 **Duplicate Protection**\nEnabled\n\n"
                "ℹ️ The worker maintains the real MTProto connection. Telegram controls actual visible presence."
            ) + UI.ready(self.settings.owner_name), "result")

        @self.command("off", "Stop only online worker", "system")
        async def off_command(event, parsed):
            stopped = await self.workers.stop("online_worker")
            if not stopped:
                await self.reply(event, UI.info(
                    "ONLINE SYSTEM ALREADY STOPPED",
                    "📡 No active online worker was found."
                ), "result")
                return
            await self.reply(event, UI.info(
                "ONLINE SYSTEM STOPPED",
                "🔴 **Online Worker**\nStopped\n\n"
                "Other persistent features are not modified by `.off`."
            ) + UI.ready(self.settings.owner_name), "result")

        @self.command("ping", "Measure meaningful local latency", "system")
        async def ping_command(event, parsed):
            t0 = time.perf_counter()
            message = await self.reply(event, UI.loading("SYSTEM LATENCY", "Measuring confirmed local metrics..."), "progress")
            db_ms = None
            try:
                d0 = time.perf_counter()
                assert self.db.conn
                async with self.db.conn.execute("SELECT 1") as cursor:
                    await cursor.fetchone()
                db_ms = (time.perf_counter() - d0) * 1000
            except Exception:
                pass
            processing = (time.perf_counter() - t0) * 1000
            body = f"⚡ **Processing**\n`{processing:.2f} ms`\n\n"
            body += f"💾 **Database**\n`{db_ms:.2f} ms`\n\n" if db_ms is not None else "💾 **Database**\nUnavailable\n\n"
            body += "🌐 **Telegram**\nNot measured — no fake network latency is reported."
            await message.edit(UI.success("SYSTEM LATENCY", body))

        @self.command("info", "Show system information", "system")
        async def info_command(event, parsed):
            integrity = await self.db.integrity_check()
            uptime = int(time.monotonic() - self.started_at)
            workers = sum(1 for w in self.workers.all_status() if w.state == WorkerState.RUNNING)
            await self.reply(event, UI.info(
                "USERBOT INFORMATION",
                f"🤖 **Version**\nBerdiyorov JARVIS Userbot v1.0\n\n"
                f"📡 **Telegram Library**\nTelethon\n\n"
                f"💾 **Database Integrity**\n{integrity}\n\n"
                f"⚙️ **Active Workers**\n{workers}\n\n"
                f"⏱ **Uptime**\n{uptime}s"
            ), "result")

        @self.command("stat", "Show system dashboard", "system")
        async def stat_command(event, parsed):
            snap = await self.system.snapshot()
            running = sum(1 for state in snap.workers.values() if str(state).lower() == "running")
            counts = await self.control.counts()
            bio = await self.profile.load("bio")
            status = await self.profile.load("status")
            body = (
                f"🖥 **SYSTEM**\n⏱ Uptime: `{fmt_uptime(snap.uptime)}`\n"
                f"💾 Database: {'🟢 Healthy' if snap.database_ok else '🔴 Warning'}\n"
                f"⚙️ Workers: **{running}/{len(snap.workers)} active**\n\n━━━━━━━━━━━━\n\n"
                "**ACTIVE FEATURES**\n"
                f"📝 Auto Bio: {'🟢 Active' if bio and bio.enabled else '⚪ Off'}\n"
                f"😊 Auto Status: {'🟢 Active' if status and status.enabled else '⚪ Off'}\n"
                f"🔇 Muted Targets: {counts['muted']}\n🚫 Blocked Targets: {counts['blocked']}\n\n━━━━━━━━━━━━\n\n"
                f"**STATISTICS**\n⌨️ Registered Commands: {snap.commands}\n"
                f"📈 Commands Executed: {await self.system.command_count()}\n⚠️ Recorded Errors: {snap.errors}"
            )
            await self.reply(event, UI.info("SYSTEM DASHBOARD", body) + UI.ready(self.settings.owner_name), "result")

        @self.command("autoread", "Enable automatic read for private chats", "automation")
        async def autoread_command(event, parsed):
            mode = parsed.args[0].lower() if parsed.args else "start"
            if mode in {"status","info"}:
                state=await self.autoread.get("autoread")
                await self.reply(event, UI.info("AUTOREAD STATUS",
                    f"📖 **Private Chats**\n{'🟢 Active' if state['enabled'] else '⚪ Off'}\n\n"
                    "Groups, channels and bots are not included in this mode."),"result"); return
            if mode=="help":
                await self.reply(event,UI.info("AUTOREAD HELP","`.autoread`\n`.autoread status`\n`.autoread info`\n`.autoread test`"),"help"); return
            if mode=="test":
                await self.reply(event,UI.info("AUTOREAD TEST","Configuration is active when incoming private messages are marked read by the event engine."),"result"); return
            await self.autoread.set("autoread",True,"private")
            await self.reply(event,UI.success("AUTOREAD ENABLED",
                "📖 **Mode**\nPrivate chats\n\n🚫 **Excluded**\nGroups • Channels • Bots\n\nReal read calls are performed only for supported incoming messages."
            )+UI.ready(self.settings.owner_name),"result")

        @self.command("autoreadall", "Enable automatic read for supported chats", "automation")
        async def autoreadall_command(event, parsed):
            await self.autoread.set("autoreadall",True,"all_supported")
            await self.reply(event,UI.success("AUTOREAD ALL ENABLED",
                "📖 **Private**\nEnabled\n\n👥 **Groups**\nEnabled when Telegram permits read acknowledgement\n\n"
                "📢 **Channels**\nEnabled when supported\n\n🤖 **Bots**\nEnabled"
            )+UI.ready(self.settings.owner_name),"result")

        @self.command("unread", "Disable autoread systems", "automation")
        async def unread_command(event, parsed):
            await self.autoread.set("autoread",False,None)
            await self.autoread.set("autoreadall",False,None)
            await self.reply(event,UI.info("AUTOREAD SYSTEMS DISABLED",
                "📖 **Autoread**\nOff\n\n📚 **Autoread All**\nOff\n\nNo other feature was changed."
            )+UI.ready(self.settings.owner_name),"result")

        @self.command("taxrir", "Enable incoming message edit tracking", "tracking")
        async def taxrir_command(event, parsed):
            await self.autoread.set("edit_tracker",True,"incoming")
            await self.reply(event,UI.success("EDIT TRACKING ENABLED",
                "✏️ **Scope**\nSupported incoming messages\n\n💾 **History**\nSQLite persistent storage\n\n"
                "Original and edited text are recorded when both versions are available."
            )+UI.ready(self.settings.owner_name),"result")

        @self.command("untaxrir", "Disable edit tracking", "tracking")
        async def untaxrir_command(event, parsed):
            await self.autoread.set("edit_tracker",False,None)
            await self.reply(event,UI.info("EDIT TRACKING STOPPED",
                "✏️ Future edits will not be tracked.\n\n💾 Existing edit history was preserved."
            )+UI.ready(self.settings.owner_name),"result")

        @self.command("log", "Connect a verified Telegram log destination", "control")
        async def log_command(event, parsed):
            if not parsed.args:
                await self.reply(event,UI.warning("LOG TARGET NOT PROVIDED",
                    "**WHAT**\nA channel or chat ID is required.\n\n**FIX**\nUse:\n`.log CHANNEL_ID`"),"result"); return
            target=parsed.args[0]
            try:
                entity,test=await self.logger.set_channel(target)
                title=getattr(entity,"title",None) or getattr(entity,"username",None) or str(target)
                await self.reply(event,UI.success("LOG CHANNEL CONNECTED",
                    f"📢 **Channel**\n{title}\n\n🆔 **ID**\n`{target}`\n\n📡 **Connection**\nVerified\n\n📨 **Test Message**\nSent"
                )+UI.ready(self.settings.owner_name),"persistent")
            except Exception as exc:
                await self.reply(event,UI.error("LOG CONNECTION FAILED",
                    f"**WHY**\n`{type(exc).__name__}: {str(exc)[:250]}`\n\n"
                    "**FIX**\nCheck the ID, account access and send permission."),"critical")





        def fmt_uptime(seconds):
            seconds=max(0,int(seconds))
            h,rem=divmod(seconds,3600); m,s=divmod(rem,60)
            return f"{h:02}:{m:02}:{s:02}"

        @self.command("calc","Safely calculate mathematical expressions","tools")
        async def calc_command(event,parsed):
            mode=parsed.args[0].lower() if parsed.args else None
            if mode=="help":
                await self.reply(event,UI.info("CALCULATOR HELP",
                    "`.calc 2+2`\n`.calc (50+20)*3`\n`.calc sqrt(144)`\n`.calc 2^10`\n`.calc 20%`\n\n"
                    "Modes:\n`.calc history`\n`.calc examples`\n\nOnly a restricted mathematical parser is used. Python `eval()` is never used."
                ),"help"); return
            if mode=="examples":
                await self.reply(event,UI.info("CALCULATOR EXAMPLES",
                    "`.calc 2+2`\n`.calc 50*20`\n`.calc (50+20)*3`\n`.calc sqrt(144)`\n`.calc 2^10`\n`.calc 20%`"
                ),"help"); return
            if mode=="history":
                history=getattr(self,"_calc_history",{}).get(event.chat_id,[])
                body="No calculations yet." if not history else "\n".join(
                    f"`{x.expression}` = **{x.result}**" for x in history[-10:][::-1])
                await self.reply(event,UI.info("CALCULATION HISTORY",body),"result"); return
            expression=" ".join(parsed.args)
            try:
                result=self.calculator.calculate(expression)
            except CalculatorError as exc:
                await self.reply(event,UI.warning("CALCULATION COULD NOT BE COMPLETED",
                    f"**WHY**\n{exc}\n\n**EXAMPLE**\n`.calc (50+20)*3`"),"result"); return
            if not hasattr(self,"_calc_history"): self._calc_history={}
            self._calc_history.setdefault(event.chat_id,[]).append(result)
            self._calc_history[event.chat_id]=self._calc_history[event.chat_id][-30:]
            await self.reply(event,UI.success("CALCULATION RESULT",
                f"🧮 **Expression**\n`{result.expression}`\n\n📊 **Result**\n**{result.result}**"
            ),"result")

        @self.command("del","Delete recent messages sent by the account","tools")
        async def del_command(event,parsed):
            token=parsed.args[0].lower() if parsed.args else None
            if token=="help":
                await self.reply(event,UI.info("DELETE HELP",
                    "`.del 1`\n`.del 50`\n`.del 30m`\n`.del 1h`\n`.del today`\n\n"
                    "Modes:\n`.del status`\n`.del cancel`\n`.del examples`\n\nThe task only targets messages sent by your own account. Actual Telegram permissions still apply."
                ),"help"); return
            if token=="examples":
                await self.reply(event,UI.info("DELETE EXAMPLES",
                    "`.del 1`\n`.del 50`\n`.del 100`\n`.del 30m`\n`.del 1h`\n`.del today`"
                ),"help"); return
            if token=="status":
                active=self.deleter.active(event.chat_id)
                await self.reply(event,UI.info("DELETE STATUS",
                    "🟢 Cleaning is currently running." if active else "⚪ No deletion task is running in this chat."
                ),"result"); return
            if token=="cancel":
                cancelled=self.deleter.cancel(event.chat_id)
                await self.reply(event,UI.info("DELETE CANCEL",
                    "🟡 Cancellation requested. The current safe step will finish first." if cancelled else "No active deletion task was found."
                ),"result"); return
            if not token:
                await self.reply(event,UI.warning("DELETE AMOUNT NOT DETECTED",
                    "**WHAT**\nI could not determine how many messages to process.\n\n"
                    "**FIX**\nUse `.del 50`, `.del 1h`, or `.del today`."
                ),"result"); return

            limit=None; since=None
            try:
                if token.isdigit():
                    limit=int(token)
                    if limit < 1 or limit > 5000:
                        raise ValueError("Amount must be between 1 and 5000.")
                else:
                    _,since=self.deleter.parse_period(token)
            except ValueError as exc:
                await self.reply(event,UI.warning("INVALID DELETE REQUEST",
                    f"**WHY**\n{exc}\n\n**EXAMPLE**\n`.del 50` or `.del 30m`"
                ),"result"); return

            progress_msg=await self.reply(event,UI.loading("CLEANING MESSAGES","Scanning your own messages..."),"progress")
            async def progress(result,index,total):
                percent=int(index*100/total)
                filled=min(10,percent//10)
                bar="█"*filled+"░"*(10-filled)
                try:
                    await progress_msg.edit(
                        UI.header("CLEANING MESSAGES")+
                        f"\n\n{bar}  **{percent}%**\n\n"
                        f"📨 **Found**\n{result.found}\n\n"
                        f"🗑 **Deleted**\n{result.deleted}\n\n"
                        f"⚠️ **Errors**\n{result.errors}"
                    )
                except Exception:
                    pass

            try:
                result=await self.deleter.delete_recent_own(event,limit=limit,since=since,progress=progress)
                status="🟡 Cancelled safely" if result.cancelled else "🟢 Task finished"
                await progress_msg.edit(
                    UI.header("MESSAGE CLEANUP RESULT")+
                    f"\n\n{status}\n\n"
                    f"📨 **Found**\n{result.found}\n\n"
                    f"🗑 **Deleted**\n{result.deleted}\n\n"
                    f"⏭ **Skipped**\n{result.skipped}\n\n"
                    f"⚠️ **Errors**\n{result.errors}"
                )
                # Progress response already exists; record it only if response manager supports tracking.
            except RuntimeError as exc:
                try:
                    await progress_msg.edit(UI.warning("DELETE TASK ALREADY RUNNING",str(exc)))
                except Exception:
                    pass
            except Exception as exc:
                try:
                    await progress_msg.edit(UI.error("DELETE FAILED",
                        f"**WHY**\n`{type(exc).__name__}: {str(exc)[:250]}`\n\nNo unconfirmed deletion success was reported."
                    ))
                except Exception:
                    pass

        def parse_rotation(raw_args):
            text=" ".join(raw_args).strip()
            if not text:
                raise ValueError("No values were provided.")
            interval=60
            if " : " in text:
                text, tail=text.rsplit(" : ",1)
                if not tail.strip().isdigit(): raise ValueError("Interval must be a positive number of seconds.")
                interval=int(tail.strip())
            elif ":" in text and text.rsplit(":",1)[1].strip().isdigit():
                text,tail=text.rsplit(":",1); interval=int(tail.strip())
            if interval<30: raise ValueError("Minimum interval is 30 seconds.")
            mode="random"
            lower=text.lower().strip()
            if lower.endswith(" random"):
                text=text[:-7].strip(); mode="random"
            elif lower.endswith(" sequence"):
                text=text[:-9].strip(); mode="sequence"
            values=[x.strip() for x in text.split("|") if x.strip()]
            if not values: raise ValueError("No valid values were found.")
            if len(set(values))!=len(values): raise ValueError("Duplicate values are not allowed.")
            return values,mode,interval

        @self.command("bio","Configure automatic Telegram bio rotation","profile")
        async def bio_command(event,parsed):
            mode=parsed.args[0].lower() if parsed.args else None
            if mode in {"status","current","original"}:
                state=await self.profile.load("bio")
                current=await self.profile.current_bio()
                if mode=="current":
                    await self.reply(event,UI.info("CURRENT BIO",current or "No bio is currently set."),"result");return
                if mode=="original":
                    await self.reply(event,UI.info("ORIGINAL BIO",(state.previous if state and state.previous is not None else "No backup is available.")),"result");return
                body="⚪ Off"
                if state: body=f"{'🟢 Active' if state.enabled else '⚪ Off'}\n\n🔄 Mode: {state.mode}\n⏱ Interval: {state.interval}s\n📝 Entries: {len(state.values)}"
                await self.reply(event,UI.info("BIO SYSTEM STATUS",body),"result");return
            if mode=="help":
                await self.reply(event,UI.info("BIO HELP","`.bio Hello`\n`.bio Hello | World`\n`.bio Hello | World : 60`\n"
                    "`.bio Hello | World random : 60`\n`.bio Hello | World sequence : 60`\n\nModes:\n`.bio status`\n`.bio current`\n`.bio original`\n`.bio examples`"),"help");return
            if mode=="examples":
                await self.reply(event,UI.info("BIO EXAMPLES","`.bio Hello`\n`.bio Online | Working : 60`\n`.bio One | Two sequence : 45`"),"help");return
            try: values,rotation,interval=parse_rotation(parsed.args)
            except ValueError as exc:
                await self.reply(event,UI.warning("INVALID BIO CONFIGURATION",f"**WHY**\n{exc}\n\n**EXAMPLE**\n`.bio Hello | World sequence : 60`"),"result");return
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
                await self.logger.event("BIO CHANGE",f"Mode: {rotation}\nInterval: {interval}s\nEntries: {len(values)}")
                await self.reply(event,UI.success("BIO SYSTEM ENABLED",
                    f"📝 **Entries**\n{len(values)}\n\n🔄 **Mode**\n{rotation.title()}\n\n⏱ **Interval**\n{interval} seconds\n\n"
                    f"✅ **First Bio**\n{first}"
                )+UI.ready(self.settings.owner_name),"result")
            except Exception as exc:
                await self.reply(event,UI.error("BIO UPDATE FAILED",f"**WHY**\n`{type(exc).__name__}: {str(exc)[:250]}`\n\nNo activation success was claimed."),"critical")

        @self.command("unbio","Stop automatic bio rotation","profile")
        async def unbio_command(event,parsed):
            state=await self.profile.stop("bio")
            if not state:
                await self.reply(event,UI.info("BIO SYSTEM ALREADY OFF","No saved automatic bio configuration was found."),"result");return
            restored=False; restore_error=None
            if state.previous is not None:
                try: await self.profile.set_bio(state.previous); restored=True
                except Exception as exc: restore_error=type(exc).__name__
            body="🛑 **Rotation**\nStopped"
            body+= "\n\n♻️ **Previous Bio**\nRestored" if restored else "\n\n⚠️ **Previous Bio**\nNot restored"
            if restore_error: body+=f"\nReason: `{restore_error}`"
            await self.reply(event,UI.info("BIO SYSTEM STOPPED",body)+UI.ready(self.settings.owner_name),"result")

        @self.command("autostatus","Configure automatic emoji status","profile")
        async def autostatus_command(event,parsed):
            mode=parsed.args[0].lower() if parsed.args else None
            if mode in {"status","current","info"}:
                state=await self.profile.load("status")
                body="⚪ Off" if not state else f"{'🟢 Active' if state.enabled else '⚪ Off'}\n\n🔄 Mode: {state.mode}\n⏱ Interval: {state.interval}s\n😊 Entries: {len(state.values)}"
                await self.reply(event,UI.info("AUTO STATUS",body),"result");return
            if mode=="help":
                await self.reply(event,UI.info("AUTOSTATUS HELP","`.autostatus EMOJI_ID`\n`.autostatus ID1 ID2 ID3`\n"
                    "`.autostatus ID1 ID2 sequence : 60`\n\nModes:\n`.autostatus status`\n`.autostatus current`\n`.autostatus examples`"),"help");return
            if mode=="examples":
                await self.reply(event,UI.info("AUTOSTATUS EXAMPLES","`.autostatus 5276098269204754305`\n`.autostatus 111 222 sequence : 60`"),"help");return
            try: values,rotation,interval=parse_rotation([" ".join(parsed.args).replace(" "," | ",0)])
            except ValueError:
                # Status IDs are space-separated, so parse independently.
                raw=" ".join(parsed.args); interval=60
                if ":" in raw and raw.rsplit(":",1)[1].strip().isdigit(): raw,tail=raw.rsplit(":",1); interval=int(tail.strip())
                rotation="sequence" if raw.lower().strip().endswith(" sequence") else "random"
                raw=raw.rsplit(" ",1)[0] if raw.lower().strip().endswith((" sequence"," random")) else raw
                values=[x for x in raw.split() if x]
                if not values or any(not x.isdigit() for x in values) or interval<30:
                    await self.reply(event,UI.warning("INVALID STATUS CONFIGURATION","Use numeric custom emoji IDs and an interval of at least 30 seconds."),"result");return
            previous=None
            state=RotationState(True,values,rotation,interval,previous)
            await self.profile.save("status",state)
            worker=self.workers.status("status_worker")
            if not worker or worker.state != WorkerState.RUNNING:
                await self.workers.start("status_worker",self.profile.status_worker)
            await self.reply(event,UI.warning("AUTO STATUS SAVED WITH API LIMITATION",
                f"😊 **Configured IDs**\n{len(values)}\n\n🔄 **Mode**\n{rotation.title()}\n\n⏱ **Interval**\n{interval}s\n\n"
                "The installed Telethon/API layer has not yet been verified for emoji-status updates. Configuration and worker state are saved, but no status change is claimed."
            )+UI.ready(self.settings.owner_name),"result")

        @self.command("unstatus","Stop automatic emoji status","profile")
        async def unstatus_command(event,parsed):
            state=await self.profile.stop("status")
            if not state:
                await self.reply(event,UI.info("AUTO STATUS ALREADY OFF","No saved automatic status configuration was found."),"result");return
            await self.reply(event,UI.info("AUTO STATUS STOPPED","Worker configuration disabled. No fake restoration claim was made because status API compatibility is not yet verified.")+UI.ready(self.settings.owner_name),"result")

        async def resolve_control_target(event, parsed, start=0):
            explicit=parsed.args[start] if len(parsed.args)>start else None
            try:
                return await self.targets.resolve(event,explicit)
            except TargetNotFound:
                await self.reply(event,UI.warning("TARGET NOT DETECTED",
                    "I could not determine the target.\n\n"
                    "**AVAILABLE METHODS**\n"
                    "👤 Username: `.mute @username`\n"
                    "🆔 ID: `.mute 123456789`\n"
                    "💬 Reply to a user, then use the command\n"
                    "📱 Use the command inside a private chat"
                )+UI.ready(self.settings.owner_name),"result")
                return None

        @self.command("mute","Add a user to local mute policy","control")
        async def mute_command(event,parsed):
            mode=parsed.args[0].lower() if parsed.args else None
            if mode=="help":
                await self.reply(event,UI.info("MUTE HELP",
                    "`.mute @username`\n`.mute 123456789`\nReply + `.mute`\nPrivate chat + `.mute`\n\n"
                    "Modes:\n`.mute status`\n`.mute list`\n`.mute info @username`\n`.mute check @username`"),"help"); return
            if mode=="status":
                c=await self.control.counts()
                await self.reply(event,UI.info("MUTE STATUS",f"🔇 **Active local mute targets**\n{c['muted']}\n\n"
                    "This feature stores a local userbot policy; Telegram user accounts do not provide one universal server-side mute-user API."),"result"); return
            if mode=="list":
                rows=await self.control.mute_list()
                body="No active muted targets." if not rows else "\n\n".join(
                    f"{i}. **@{u}**" if u else f"{i}. **{d}**\n   🆔 `{uid}`" for i,(uid,u,d) in enumerate(rows[:30],1))
                await self.reply(event,UI.info("MUTED TARGETS",body),"result"); return
            if mode in {"info","check"}:
                target=await resolve_control_target(event,parsed,1)
                if not target:return
                row=await self.control.muted(target.user_id)
                active=bool(row and row[3])
                await self.reply(event,UI.info("MUTE CHECK",
                    f"👤 **Target**\n{target.display_name}\n\n🔇 **Local policy**\n{'🟢 Muted' if active else '⚪ Not muted'}"),"result"); return
            target=await resolve_control_target(event,parsed)
            if not target:return
            await self.control.mute(target)
            await self.logger.event("MUTE",f"User: {target.display_name}\nID: `{target.user_id}`")
            await self.reply(event,UI.success("LOCAL MUTE ENABLED",
                f"👤 **Target**\n{target.display_name}\n\n🆔 **ID**\n`{target.user_id}`\n\n"
                "🔇 **State**\nActive local userbot mute policy\n\n"
                "Telegram does not expose a universal server-side mute-user action for personal accounts, so this result does not pretend to change remote account state."
            )+UI.ready(self.settings.owner_name),"result")

        @self.command("unmute","Remove a user from local mute policy","control")
        async def unmute_command(event,parsed):
            if parsed.args and parsed.args[0].lower()=="help":
                await self.reply(event,UI.info("UNMUTE HELP","`.unmute @username`\nReply + `.unmute`\nPrivate chat + `.unmute`"),"help");return
            if parsed.args and parsed.args[0].lower()=="status":
                c=await self.control.counts()
                await self.reply(event,UI.info("UNMUTE STATUS",f"🔇 Active local mute targets: {c['muted']}"),"result");return
            target=await resolve_control_target(event,parsed)
            if not target:return
            changed=await self.control.unmute(target)
            if not changed:
                await self.reply(event,UI.info("TARGET WAS NOT MUTED",f"**{target.display_name}** has no active local mute policy."),"result");return
            await self.logger.event("UNMUTE",f"User: {target.display_name}\nID: `{target.user_id}`")
            await self.reply(event,UI.success("LOCAL MUTE REMOVED",f"👤 **Target**\n{target.display_name}\n\n🔊 Local policy disabled.")+UI.ready(self.settings.owner_name),"result")

        @self.command("block","Block a Telegram user","control")
        async def block_command(event,parsed):
            mode=parsed.args[0].lower() if parsed.args else None
            if mode=="help":
                await self.reply(event,UI.info("BLOCK HELP","`.block @username`\n`.block 123456789`\nReply + `.block`\nPrivate chat + `.block`\n\n"
                    "Modes:\n`.block status`\n`.block list`\n`.block info @username`\n`.block check @username`"),"help");return
            if mode=="status":
                c=await self.control.counts()
                await self.reply(event,UI.info("BLOCK STATUS",f"🚫 **Active blocked targets**\n{c['blocked']}"),"result");return
            if mode=="list":
                rows=await self.control.block_list()
                body="No active blocked targets." if not rows else "\n\n".join(
                    f"{i}. **@{u}**" if u else f"{i}. **{d}**\n   🆔 `{uid}`" for i,(uid,u,d) in enumerate(rows[:30],1))
                await self.reply(event,UI.info("BLOCKED TARGETS",body),"result");return
            if mode in {"info","check"}:
                target=await resolve_control_target(event,parsed,1)
                if not target:return
                row=await self.control.blocked(target.user_id)
                active=bool(row and row[3])
                await self.reply(event,UI.info("BLOCK CHECK",f"👤 **Target**\n{target.display_name}\n\n🚫 **State**\n{'🟢 Blocked' if active else '⚪ Not blocked'}"),"result");return
            target=await resolve_control_target(event,parsed)
            if not target:return
            try:
                await self.control.block(target)
                await self.logger.event("BLOCK",f"User: {target.display_name}\nID: `{target.user_id}`")
                await self.reply(event,UI.success("USER BLOCKED",
                    f"👤 **Target**\n{target.display_name}\n\n🆔 **ID**\n`{target.user_id}`\n\n🚫 **Telegram Action**\nConfirmed"
                )+UI.ready(self.settings.owner_name),"result")
            except Exception as exc:
                await self.reply(event,UI.error("BLOCK FAILED",
                    f"**WHY**\n`{type(exc).__name__}: {str(exc)[:250]}`\n\nNo success was recorded."),"critical")

        @self.command("unblock","Unblock a Telegram user","control")
        async def unblock_command(event,parsed):
            if parsed.args and parsed.args[0].lower()=="help":
                await self.reply(event,UI.info("UNBLOCK HELP","`.unblock @username`\nReply + `.unblock`\nPrivate chat + `.unblock`"),"help");return
            if parsed.args and parsed.args[0].lower()=="status":
                c=await self.control.counts()
                await self.reply(event,UI.info("UNBLOCK STATUS",f"🚫 Active blocked targets: {c['blocked']}"),"result");return
            target=await resolve_control_target(event,parsed)
            if not target:return
            try:
                changed=await self.control.unblock(target)
                if not changed:
                    await self.reply(event,UI.info("TARGET WAS NOT BLOCKED",f"**{target.display_name}** has no active blocked record."),"result");return
                await self.logger.event("UNBLOCK",f"User: {target.display_name}\nID: `{target.user_id}`")
                await self.reply(event,UI.success("USER UNBLOCKED",
                    f"👤 **Target**\n{target.display_name}\n\n🔓 **Telegram Action**\nConfirmed"
                )+UI.ready(self.settings.owner_name),"result")
            except Exception as exc:
                await self.reply(event,UI.error("UNBLOCK FAILED",
                    f"**WHY**\n`{type(exc).__name__}: {str(exc)[:250]}`\n\nNo success was recorded."),"critical")

        @self.command("story", "Track and inspect user stories", "tracking")
        async def story_command(event, parsed):
            mode = parsed.args[0].lower() if parsed.args else None
            modes = {"status", "list", "info", "check", "help", "examples"}

            if mode == "help":
                await self.reply(event, UI.info(
                    "STORY HELP",
                    "`.story @username` — add target\n"
                    "`.story 123456789` — add by ID\n"
                    "Reply + `.story` — use reply sender\n"
                    "Private chat + `.story` — use current user\n\n"
                    "Modes:\n`.story status`\n`.story list`\n"
                    "`.story info @username`\n`.story check @username`"
                ), "help")
                return

            if mode == "examples":
                await self.reply(event, UI.info(
                    "STORY EXAMPLES",
                    "`.story @username`\n`.story 123456789`\n"
                    "`.story status`\n`.story list`\n"
                    "`.story check @username`"
                ), "help")
                return

            if mode == "status":
                data = await self.story.stats()
                worker = self.workers.status("story_worker")
                state = "🟢 Active" if worker and worker.state == WorkerState.RUNNING else "⚪ Idle"
                await self.reply(event, UI.info(
                    "STORY SYSTEM STATUS",
                    f"👥 **Active Targets**\n{data['active']}\n\n"
                    f"😊 **Confirmed Reactions**\n{data['reactions']}\n\n"
                    f"⚠️ **Errors**\n{data['errors']}\n\n"
                    f"⚙️ **Worker**\n{state}"
                ), "result")
                return

            if mode == "list":
                targets = await self.story.list_targets()
                if not targets:
                    await self.reply(event, UI.info(
                        "STORY TARGETS",
                        "No active targets yet.\n\nAdd one with:\n`.story @username`"
                    ), "result")
                    return
                lines = []
                for i, target in enumerate(targets[:20], 1):
                    name = f"@{target.username}" if target.username else target.display_name
                    reaction = target.reaction or "Default"
                    lines.append(f"{i}. **{name}**\n   😊 {reaction}\n   🟢 Active")
                await self.reply(event, UI.info(
                    "STORY TARGETS",
                    "\n\n".join(lines)
                ), "result")
                return

            if mode in {"info", "check"}:
                explicit = parsed.args[1] if len(parsed.args) > 1 else None
                try:
                    target = await self.targets.resolve(event, explicit)
                except TargetNotFound:
                    await self.reply(event, UI.warning(
                        "TARGET NOT DETECTED",
                        "Use `.story info @username` or reply to a user's message."
                    ), "result")
                    return

                if mode == "info":
                    saved = await self.story.get_target(target.user_id)
                    if not saved:
                        await self.reply(event, UI.info(
                            "STORY TARGET INFO",
                            f"👤 **User**\n{target.display_name}\n\n"
                            "⚪ Tracking is not active."
                        ), "result")
                        return
                    name = f"@{saved.username}" if saved.username else saved.display_name
                    await self.reply(event, UI.info(
                        "STORY TARGET INFO",
                        f"👤 **User**\n{name}\n\n🆔 **ID**\n`{saved.user_id}`\n\n"
                        f"📡 **Tracking**\n{'Active' if saved.active else 'Stopped'}\n\n"
                        f"😊 **Reaction**\n{saved.reaction or 'Default'}"
                    ), "result")
                    return

                result = await self.story.check_target(target)
                if not result["supported"]:
                    await self.reply(event, UI.warning(
                        "STORY CHECK COMPLETED WITH LIMITATION",
                        f"👤 **Target**\n{target.display_name}\n\n"
                        "📡 **Check State**\nTarget recorded as checked\n\n"
                        "⚠️ **API Compatibility**\n"
                        + result["reason"] +
                        "\n\nNo reaction was claimed or recorded."
                    ), "result")
                    return

            # Default: target + optional custom emoji ID
            explicit = parsed.args[0] if parsed.args else None
            reaction = parsed.args[1] if len(parsed.args) > 1 else None
            try:
                target = await self.targets.resolve(event, explicit)
            except TargetNotFound:
                await self.reply(event, UI.warning(
                    "TARGET NOT DETECTED",
                    "I could not determine who you want to track.\n\n"
                    "**AVAILABLE METHODS**\n"
                    "👤 `.story @username`\n"
                    "🆔 `.story 123456789`\n"
                    "💬 Reply to a user, then `.story`\n"
                    "📱 Use `.story` inside a private chat"
                ) + UI.ready(self.settings.owner_name), "result")
                return

            if reaction and not reaction.isdigit():
                await self.reply(event, UI.warning(
                    "INVALID CUSTOM EMOJI ID",
                    "The supplied custom emoji ID must be numeric.\n\n"
                    "Example:\n`.story @username 5276098269204754305`"
                ), "result")
                return

            created = await self.story.add_target(target, reaction)
            worker = self.workers.status("story_worker")
            if not worker or worker.state != WorkerState.RUNNING:
                story_worker = StoryWorker(self.story)
                await self.workers.start("story_worker", story_worker.run)

            check = await self.story.check_target(target)
            name = f"@{target.username}" if target.username else target.display_name
            title = "STORY TRACKING ENABLED" if created else "STORY TRACKING UPDATED"
            api_note = (
                "📖 **Existing Stories**\nChecked with current build compatibility"
                if check["supported"] else
                "⚠️ **Story API**\nMonitoring target saved, but reaction execution is disabled until API compatibility is verified."
            )
            await self.reply(event, UI.success(
                title,
                f"👤 **Target**\n{name}\n\n"
                f"🆔 **ID**\n`{target.user_id}`\n\n"
                "📡 **Monitoring**\nActive\n\n"
                f"😊 **Reaction**\n{reaction or 'Configured default when supported'}\n\n"
                + api_note +
                "\n\n**NEXT ACTIONS**\n"
                "• `.story status`\n• `.story list`\n"
                f"• `.unstory {target.user_id}`"
            ) + UI.ready(self.settings.owner_name), "result")

        @self.command("unstory", "Stop tracking a user's stories", "tracking")
        async def unstory_command(event, parsed):
            mode = parsed.args[0].lower() if parsed.args else None
            if mode == "status":
                data = await self.story.stats()
                await self.reply(event, UI.info(
                    "STORY TRACKING STATUS",
                    f"👥 Active targets: {data['active']}"
                ), "result")
                return
            if mode == "help":
                await self.reply(event, UI.info(
                    "UNSTORY HELP",
                    "`.unstory @username`\n`.unstory 123456789`\n"
                    "Reply + `.unstory`\nPrivate chat + `.unstory`"
                ), "help")
                return
            try:
                explicit = parsed.args[0] if parsed.args else None
                target = await self.targets.resolve(event, explicit)
            except TargetNotFound:
                await self.reply(event, UI.warning(
                    "TARGET NOT DETECTED",
                    "Specify a user, reply to one, or use this command in a private chat."
                ), "result")
                return
            removed = await self.story.remove_target(target.user_id)
            if not removed:
                await self.reply(event, UI.info(
                    "STORY TRACKING NOT ACTIVE",
                    f"No active tracking target was found for **{target.display_name}**."
                ), "result")
                return
            await self.reply(event, UI.success(
                "STORY TRACKING STOPPED",
                f"👤 **Target**\n{target.display_name}\n\n"
                "Future monitoring is disabled. Existing action history is preserved."
            ) + UI.ready(self.settings.owner_name), "result")


    async def start(self):
        await self.db.connect()
        if await self.db.integrity_check() != "ok":
            raise RuntimeError("SQLite integrity check failed.")

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
            all_state=await self.autoread.get("autoreadall")
            private_state=await self.autoread.get("autoread")
            should_read=all_state["enabled"] or (private_state["enabled"] and event.is_private)
            if should_read:
                try:
                    await self.client.send_read_acknowledge(event.chat_id, max_id=event.id)
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
                body = f"You entered:\n`.{parsed.name}`\n\n"
                body += f"Did you mean:\n`.{suggestion}`" if suggestion else "Use `.help` to see available commands."
                await self.reply(event, UI.warning("COMMAND NOT FOUND", body), "result")
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
                    "COMMAND COULD NOT COMPLETE",
                    f"**WHAT**\nThe operation stopped unexpectedly.\n\n"
                    f"**WHY**\n`{type(exc).__name__}`\n\n"
                    "**FIX**\nCheck the input, permissions or connection and try again."
                ), "critical")

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))
            except (NotImplementedError, RuntimeError):
                pass

        await self.client.start()
        me = await self.client.get_me()
        print(f"USERBOT ONLINE: {getattr(me, 'id', 'unknown')}")
        print(f"Ready, {self.settings.owner_name}.")
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
