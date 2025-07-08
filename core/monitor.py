import asyncio, logging
class Monitor:
    def __init__(self, upbit, hedge, oms):
        self.upbit, self.hedge, self.oms = upbit, hedge, oms
        self.log = logging.getLogger("Monitor")
    async def run(self):
        fail = 0
        while True:
            try:
                await self.upbit.ccxt_ex.fetch_time()
                await self.hedge.ccxt_ex.fetch_time()
                fail = 0
            except Exception as e:
                fail += 1
                self.log.warning("ping fail %d/2: %s", fail, e)
                if fail >= 2:
                    await self.oms.emergency_flat()
                    raise
            await asyncio.sleep(30)
