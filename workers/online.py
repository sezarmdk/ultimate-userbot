import asyncio

class OnlineWorker:
    def __init__(self, client):
        self.client = client

    async def run(self):
        # Real MTProto connection keepalive. This does not fake permanent online state.
        try:
            while True:
                if not self.client.is_connected():
                    await self.client.connect()
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            raise
