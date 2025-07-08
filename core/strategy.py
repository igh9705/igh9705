import asyncio, decimal as D
from .models import StratCfg
import time
import logging
class Strategy:
    def __init__(self,
                 cfg,               # StratCfg
                 mkt_q,             # asyncio.Queue
                 ord_q,             # asyncio.Queue
                 loop_metric,       # prometheus_client.Summary
                 loop_ms: int = 100
                 ):
        self.cfg        = cfg
        self.mkt_q      = mkt_q
        self.ord_q      = ord_q
        self.loop_metric= loop_metric
        self.loop_ms = loop_ms
        self.loop_s     = loop_ms / 1000     # 100 ms → 0.1
        self.snap       = {}
        self.log        = logging.getLogger("Strategy")

    async def run(self):
        while True:
            start = time.perf_counter()

            # 1) 큐 비우기
            try:
                while True:
                    ev = self.mkt_q.get_nowait()
                    self.snap.update(ev)
            except asyncio.QueueEmpty:
                pass

            # 2) 데이터가 충분할 때만 스프레드 계산
            if {'bid','ask','bid_f','ask_f'} <= self.snap.keys():
                f_mid = (self.snap['bid_f'] + self.snap['ask_f']) / 2
                implied = (D.Decimal(1) / f_mid).quantize(D.Decimal('0.00000001'))

                buy_sp  = (implied - self.snap['ask']) / self.snap['ask']
                sell_sp = (self.snap['bid'] - implied) / self.snap['bid']

                # 주문 업데이트
                await self.ord_q.put({"side":"bid",
                                    "action":"update" if buy_sp>=self.cfg.band else "cancel",
                                    "price": self.snap['ask']})
                await self.ord_q.put({"side":"ask",
                                    "action":"update" if sell_sp>=self.cfg.band else "cancel",
                                    "price": self.snap['bid']})

                # 디버그 로그
                self.log.debug("buy_sp=%+.4f%% sell_sp=%+.4f%%",
                            float(buy_sp*100), float(sell_sp*100))

            # 루프 종료까지의 시간 기록
            self.loop_metric.observe((time.perf_counter()-start)*1000)
            await asyncio.sleep(self.loop_s)