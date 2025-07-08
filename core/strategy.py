import asyncio, decimal as D
from .models import StratCfg

class Strategy:
    def __init__(self, cfg: StratCfg, mkt_q: asyncio.Queue, ord_q: asyncio.Queue):
        self.cfg, self.mkt_q, self.ord_q = cfg, mkt_q, ord_q
        self.snap = {}                  # 최신 시장 데이터 캐시
        self.loop_metric = loop_metric
        self.log = logging.getLogger("Strategy")
    async def run(self):
        band = self.cfg.band
        while True:
            start = time.perf_counter()           # ⏱️

            # 1) 큐 비우기
            try:
                while True:
                    ev = self.mkt_q.get_nowait()
                    self.snap.update(ev)
            except asyncio.QueueEmpty:
                pass
            # 2) 데이터 충분하면 스프레드 계산
            if {'bid','ask','bid_f','ask_f'} <= self.snap.keys():
                # 선물 mid → BTC/USDT  ⇒  현물 USDT/BTC 환산
                f_mid  = (self.snap['bid_f'] + self.snap['ask_f']) / 2
                implied= (D.Decimal(1) / f_mid).quantize(D.Decimal('0.00000001'))

                buy_sp  = (implied - self.snap['ask']) / self.snap['ask']
                sell_sp = (self.snap['bid'] - implied) / self.snap['bid']

                await self.ord_q.put({"side":"bid",
                                      "action":"update" if buy_sp>=band else "cancel",
                                      "price":self.snap['ask']})
                await self.ord_q.put({"side":"ask",
                                      "action":"update" if sell_sp>=band else "cancel",
                                      "price":self.snap['bid']})
            await asyncio.sleep(0)      # cooperative, 100 ms cadence는 main에서
            self.log.debug("buy_sp=%+.4f%% sell_sp=%+.4f%%",
                float(buy_sp*100), float(sell_sp*100))
            self.loop_metric.observe( (time.perf_counter()-start)*1000 )
            await asyncio.sleep(loop_s)