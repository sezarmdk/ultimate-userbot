import asyncio

class OnlineWorker:
    """Keeps the MTProto connection alive without pretending to force Telegram online."""
    def __init__(self, client, retry_delay=5, keepalive_interval=30):
        self.client = client
        self.retry_delay = retry_delay
        self.keepalive_interval = keepalive_interval

    async def run(self):
        try:
            while True:
                try:
                    if not self.client.is_connected():
                        await self.client.connect()
                    # A lightweight authenticated request verifies the connection is usable.
                    if self.client.is_connected():
                        await self.client.get_me()
                    await asyncio.sleep(self.keepalive_interval)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Temporary network/API failures are retried by the worker.
                    await asyncio.sleep(self.retry_delay)
        except asyncio.CancelledError:
            raise
