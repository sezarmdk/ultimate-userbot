class OnlineService:
    def __init__(self, workers, client):
        self.workers = workers
        self.client = client

    async def enable(self, factory):
        return await self.workers.start("online_worker", factory)

    async def disable(self):
        return await self.workers.stop("online_worker")

    def status(self):
        return self.workers.status("online_worker")
