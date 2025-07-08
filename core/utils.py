import asyncio, time
import logging

class TokenBucket:
    def __init__(self, rps:int):
        self.capacity = rps; self.tokens = rps
        self.last     = time.monotonic()
        self.lock     = asyncio.Lock()
    async def acquire(self):
        async with self.lock:
            now = time.monotonic()
            delta = now - self.last
            self.tokens = min(self.capacity, self.tokens + delta*self.capacity)
            self.last   = now
            if self.tokens < 1:
                await asyncio.sleep((1 - self.tokens)/self.capacity)
            self.tokens -= 1
        logging.getLogger("RateLimiter").debug("token used (remain=%.1f)", self.tokens)
