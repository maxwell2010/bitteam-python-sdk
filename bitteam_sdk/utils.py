import asyncio
from asyncio import Lock
from decimal import Decimal, ROUND_DOWN

class RateLimiter:
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self._lock = Lock()

    async def acquire(self):
        while True:
            async with self._lock:
                now = asyncio.get_running_loop().time()
                self.calls = [t for t in self.calls if now - t < self.period]
                if len(self.calls) < self.max_calls:
                    self.calls.append(now)
                    return
                sleep_time = self.period - (now - self.calls[0])
            await asyncio.sleep(max(0, sleep_time))

def format_number(value: str, precision: int) -> str:
    d = Decimal(value)
    quant = Decimal('0.1') ** precision
    return str(d.quantize(quant, rounding=ROUND_DOWN))
