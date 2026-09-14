
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
                except Exception:
                    # Per-target failures are stored by the service when actionable.
                    continue
            await asyncio.sleep(self.interval)
