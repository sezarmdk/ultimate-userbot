
import asyncio

class StoryWorker:
    def __init__(self, service, interval=60):
        self.service = service
        self.interval = max(30, interval)

    async def run(self):
        while True:
            targets = await self.service.list_targets()
            for target in targets:
                try:
                    await self.service.check_target(target)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    try:
                        await self.service.db.log_error("story_worker", exc)
                    except Exception:
                        pass
                    continue
            await asyncio.sleep(self.interval)
