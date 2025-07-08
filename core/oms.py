import asyncio, decimal as D
from .utils import TokenBucket
from .exchange import ExchWrapper
from .models import StratCfg
from .fx       import FxPoller

class OMS:  
    def __init__(self,
                   spot: ExchWrapper,
                  hedge: ExchWrapper,
                  cfg: StratCfg,
                  ord_q: asyncio.Queue,
                  fx:  FxPoller):          # 🔄 ② fx 인스턴스 인자 추가
         self.spot, self.hedge, self.cfg  = spot, hedge, cfg
         self.ord_q, self.fx             = ord_q, fx
         self.open  = {'bid':None,'ask':None}
         self.limiter = TokenBucket(rps=5)
         self.orders_c = orders_counter
         self.log = logging.getLogger("OMS")

    async def _size_btc(self, price_usdt:D.Decimal)->float:
         krw_per_usdt = self.fx.price      # 🔄 ③ 실시간 환율 사용
         if krw_per_usdt == 0:
             return 0.0                   # 아직 환율 못받음 → 주문 보류
         nominal_usdt = D.Decimal(self.cfg.order_size_krw) / krw_per_usdt
         btc_amount   = (nominal_usdt * price_usdt).quantize(D.Decimal('0.00000001'))
         return float(btc_amount)
    
    async def run(self):
        while True:
            cmd = await self.ord_q.get()
            side, act = cmd["side"], cmd["action"]
            if act == "update":
                await self._update(side, cmd["price"])
            elif act == "cancel":
                await self._cancel(side)

    async def _update(self, side, price):
        qty = await self._size_btc(price)
        if self.open[side]:
            await self._cancel(side)
        await self.limiter.acquire()
        spot_side = "buy" if side=="bid" else "sell"
        ord = await self.spot.limit(spot_side, qty, float(price))
        self.open[side] = ord["id"]

        hedge_side = "sell" if side=="bid" else "buy"
        await self.hedge.market(hedge_side, qty)   # 즉시 헷지
        self.orders_c.labels(side=side).inc()   # 🔢 카운터 +1

    async def _cancel(self, side):
        if not self.open[side]: return
        await self.limiter.acquire()
        await self.spot.cancel(self.open[side])
        self.open[side] = None

    # --- 긴급 청산 (모니터용)
    async def emergency_flat(self):
        self.log.warning("EMERGENCY FLAT start")
        for s in ('bid','ask'):
            if self.open_orders[s]:
                await self._cancel_order(s)
        # hedge 포지션 정리
        await self.hedge.market("buy", 999)   # ← 실제 구현 시 포지션 사이즈 조회 후 반대 주문
        self.log.warning("EMERGENCY FLAT done")
