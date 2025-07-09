# core/order_poller.py
import asyncio, logging, decimal as D
from typing import Dict, Set


class UpbitOrderPoller:
    """
    ① OMS 가 생성한 주문 id 를 watch_set 에 추가
    ② 1초마다 fetch_order(id) 호출 → 체결/취소 여부 확인
    ③ filled > 0 이면 fill_q 로 이벤트 전파
    """
    def __init__(self,
                 upbit,                       # ExchWrapper (ccxt.upbit)
                 watch_set: Set[str],
                 fill_q: asyncio.Queue,
                 poll_ms: int = 1000):
        self.upbit     = upbit
        self.watch_set = watch_set           # 공유 set() – OMS 가 주문 id push
        self.fill_q    = fill_q
        self.poll_ms   = poll_ms
        self.log       = logging.getLogger("UpbitOrderPoller")

    async def run(self):
        while True:
            await self._poll_once()
            await asyncio.sleep(self.poll_ms / 1000)

    async def _poll_once(self):
        to_remove = set()
        for oid in list(self.watch_set):
            try:
                ord = await self.upbit.ccxt_ex.fetch_order(oid)
                if ord["status"] == "closed":
                    filled = D.Decimal(ord["filled"])
                    if filled > 0:
                        side = ord["side"]             # 'buy' or 'sell'
                        await self.fill_q.put({
                            "side":    side,
                            "filled":  filled
                        })
                        self.log.info("fill %s %.8f BTC id=%s", side, filled, oid)
                    to_remove.add(oid)                 # done 처리
                elif ord["status"] == "canceled":
                    to_remove.add(oid)
            except Exception as e:
                self.log.warning("fetch_order %s error: %s", oid, e)

        self.watch_set -= to_remove                    # 완료·취소 제거
