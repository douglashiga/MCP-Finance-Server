import asyncio
import time

class RateLimiter:
    def __init__(self, calls_per_second=5):
        self.delay = 1.0 / calls_per_second
        self.last_call = 0
        self._lock = asyncio.Lock()
        self.total_calls = 0
        self.wait_events = 0
        self.total_wait_seconds = 0.0

    async def wait(self):
        async with self._lock:
            self.total_calls += 1
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.delay:
                wait_time = self.delay - elapsed
                self.wait_events += 1
                self.total_wait_seconds += wait_time
                await asyncio.sleep(wait_time)
            self.last_call = time.time()

    def snapshot(self):
        avg_wait = self.total_wait_seconds / self.wait_events if self.wait_events else 0.0
        return {
            "calls_total": self.total_calls,
            "wait_events": self.wait_events,
            "total_wait_seconds": round(self.total_wait_seconds, 6),
            "avg_wait_seconds": round(avg_wait, 6),
        }
