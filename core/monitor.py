import asyncio, logging

class Monitor:
    """
    30 초마다 두 거래소를 'ping' 하고,
    2 회 연속 실패하면 OMS.emergency_flat()을 호출해 포지션을 정리한다.
    """
    def __init__(self, upbit, hedge, oms,
                 interval_sec: int = 30, max_fail: int = 2):
        self.upbit     = upbit      # ExchWrapper
        self.hedge     = hedge      # ExchWrapper
        self.oms       = oms        # OMS 인스턴스 (emergency_flat 보유)
        self.interval  = interval_sec
        self.max_fail  = max_fail
        self.log       = logging.getLogger("Monitor")

    async def _ping(self):
        # Upbit: fetch_balance() 가 가장 가볍고 안정
        await self.upbit.ccxt_ex.fetch_ticker("BTC/USDT")
        # Binance USD‑M 은 fetch_time() 지원
        await self.hedge.ccxt_ex.fetch_time()

    async def run(self):
        fails = 0
        while True:
            try:
                await self._ping()
                if fails:
                    self.log.info("ping 회복 ✅")
                fails = 0
            except Exception as e:
                fails += 1
                self.log.warning("ping fail %d/%d: %s", fails, self.max_fail, e)
                if fails >= self.max_fail:
                    self.log.error("연속 실패 – emergency_flat 실행")
                    await self.oms.emergency_flat()
                    raise
            await asyncio.sleep(self.interval)
