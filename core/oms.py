import asyncio, decimal as D
from .utils import TokenBucket
from .exchange import ExchWrapper
from .models import StratCfg
from .fx       import FxPoller
import logging
from typing import Set
from core.utils import TokenBucket

class OMS:  
    def __init__(self,
                 spot,          # ExchWrapper (Upbit)
                 hedge,         # ExchWrapper (Binance)
                 cfg,           # StratCfg
                 ord_q,         # asyncio.Queue
                 fill_q,        # asyncio.Queue
                 orders_counter,
                 fx):
        self.spot   = spot
        self.hedge  = hedge
        self.cfg    = cfg
        self.ord_q  = ord_q
        self.fill_q = fill_q
        self.fx     = fx

        self.open       = {'bid': None, 'ask': None}
        self.watch_set  = set()
        self.orders_c   = orders_counter
        self.log        = logging.getLogger("OMS")
        self.limiter = TokenBucket(rps = 5)
        self._leverage_set = False
    async def spot_limit(self, side: str, price: D.Decimal, qty_btc: float):
        """
        Upbit 지정가 주문을 넣고 order_id 를 watch_set 에 등록
        side : 'buy' | 'sell'
        """
        ord = await self.spot.limit(side, float(price), qty_btc)
        self.watch_set.add(ord["id"])        # ← OrderPoller 가 모니터링
        self.orders_c.labels(side=side).inc()

        self.log.info("SPOT %s %.8f BTC @ %.0f KRW id=%s",
                      side.upper(), qty_btc, price, ord["id"])
        return ord
    
    async def _ensure_leverage(self):
        """
        Binanace USD‑M 기준  (set_leverage)
        호출 비용을 줄이기 위해 최초 1회만 실행
        """
        if self._leverage_set:
            return
        lev = self.cfg.hedge_leverage
        try:
            await self.hedge.ccxt_ex.fapiPrivate_post_leverage({
                "symbol": self.hedge.symbol.replace("/", ""),
                "leverage": lev
            })
            self.log.info("hedge leverage %dx 적용 완료", lev)
            self._leverage_set = True
        except Exception as e:
            self.log.warning("레버리지 설정 실패: %s", e)

    async def _size_btc(self, price_usdt: D.Decimal) -> float:
        krw_per_usdt = self.fx.price
        if krw_per_usdt == 0 or price_usdt == 0:
            return 0.0                         # 아직 데이터가 없다면 주문 보류

        nominal_usdt = D.Decimal(self.cfg.order_size_krw) / krw_per_usdt
        btc_amount   = (nominal_usdt / price_usdt).quantize(D.Decimal("0.00000001"))

        if btc_amount == 0:
            return 0.0                         # Upbit 최소 수량 미만일 때도 보류
        return float(btc_amount)
    async def hedge_market(self, side: str, qty_btc: D.Decimal):
        """
        선물 시장가 주문 — side= 'buy' or 'sell'
        qty_btc: 현물 체결 수량과 동일
        """
        await self._ensure_leverage()

        ord = await self.hedge.market(side, float(qty_btc))
        self.log.info("HEDGE %s %.8f BTC (lev %dx) id=%s",
                      side.upper(), qty_btc, self.cfg.hedge_leverage, ord["id"])
    async def _ord_loop(self):
        """Strategy 가 넣은 ord_q 명령 처리"""
        while True:
            cmd = await self.ord_q.get()
            side, act = cmd["side"], cmd["action"]
            if act == "update":
                await self._update(side, cmd["price"])
            elif act == "cancel":
                await self._cancel(side)

    async def _fill_loop(self):
        """Upbit 체결 알림 처리 → 선물 헷지"""
        while True:
            ev = await self.fill_q.get()
            side     = ev["side"]                    # spot side
            qty_btc  = ev["filled"]
            hedge_sd = "sell" if side == "buy" else "buy"
            await self.hedge_market(hedge_sd, qty_btc)

    async def run(self):
        await asyncio.gather(self._ord_loop(), self._fill_loop())

    async def _update(self, side, price):
        qty = await self._size_btc(price)
        if self.open[side]:
            await self._cancel(side)
        await self.limiter.acquire()
        spot_side = "buy" if side=="bid" else "sell"
        ord = await self.spot.limit(spot_side, qty, float(price))
        self.orders_c.labels(side=side).inc()   # 🔢 카운터 +1
        self.open[side] = ord["id"]

        hedge_side = "sell" if side=="bid" else "buy"
        await self.hedge.market(hedge_side, qty)   # 즉시 헷지

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
