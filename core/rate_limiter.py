import asyncio
import time

class RateLimiter:
    def __init__(self, calls_per_second=5):
        self.delay = 1.0 / calls_per_second
        self.last_call = 0
        self._lock = asyncio.Lock()

    async def wait(self):
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.delay:
                await asyncio.sleep(self.delay - elapsed)
            self.last_call = time.time()
