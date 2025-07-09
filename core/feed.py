# core/feed.py
import asyncio, json, logging, decimal as D
import websockets
import msgpack

class AbstractFeed:
    def __init__(self, q: asyncio.Queue):
        self.q   = q
        self.log = logging.getLogger(self.__class__.__name__)


# ────────────────────────────── Upbit (현물)
class UpbitFeed(AbstractFeed):
    URL = "wss://api.upbit.com/websocket/v1"

    def __init__(self, q, symbol="USDT-BTC"):
        super().__init__(q)
        self.symbol = symbol              # 반드시 "USDT-BTC"
        self.log    = logging.getLogger("UpbitFeed")

    async def run(self):
        while True:
            try:
                async with websockets.connect(self.URL, ping_interval=20) as ws:
                    # Upbit 는 depth 를 문자열이 아닌 숫자(int) 로 줘야 합니다.
                    sub = [
                        {"ticket": "feed"},
                        {"type": "orderbook", "codes": [self.symbol], "depth": 1}
                    ]
                    await ws.send(json.dumps(sub))
                    self.log.info("WS connected")

                    async for raw in ws:
                        j = json.loads(raw)

                        if j.get("type") != "orderbook":
                            continue

                        # ① 한 번만 프레임 구조를 찍고 싶다면
                        if not hasattr(self, "_dbg_printed"):
                            print("[DEBUG‑FRAME]", j, flush=True)
                            self._dbg_printed = True

                        units = j.get("orderbook_units")
                        if not units:
                            continue

                        best = units[0]
                        ask = D.Decimal(best["ask_price"])
                        bid = D.Decimal(best["bid_price"])

                        # ② 로그로도 확인
                        self.log.debug("ask=%s bid=%s", ask, bid)

                        await self.q.put({"ex": "spot", "ask": ask, "bid": bid})
            except Exception as e:
                self.log.warning("WS error: %s – reconnect in 5 s", e)
                await asyncio.sleep(5)


# ────────────────────────────── Binance USDT‑Perp (선물)
class BinanceFeed(AbstractFeed):
    URL_BASE = "wss://fstream.binance.com/ws"

    def __init__(self,
                 q: asyncio.Queue,
                 stream: str = "btcusdt@bookTicker"):
        super().__init__(q)
        self.stream = stream
        self.URL    = f"{self.URL_BASE}/{self.stream}"

    async def run(self):
        while True:
            try:
                async with websockets.connect(self.URL, ping_interval=20) as ws:
                    self.log.info("WS connected")
                    async for raw in ws:
                        j = json.loads(raw)
                        await self.q.put({"ex":"hedge",
                                          "ask_f": D.Decimal(j["a"]),
                                          "bid_f": D.Decimal(j["b"])})
            except Exception as e:
                self.log.warning("WS error: %s – reconnect in 5 s", e)
                await asyncio.sleep(5)
