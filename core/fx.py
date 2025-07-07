import asyncio, decimal as D, ccxt.async_support as ccxt
from pydantic import BaseModel

class FxCfg(BaseModel):
    source: str
    symbol: str
    poll_sec: int

class FxPoller:
    def __init__(self, cfg: FxCfg):
        self.cfg   = cfg
        self.price = D.Decimal("0")         # 최신 환율 (USDT 1개당 KRW)
        self._ex   = getattr(ccxt, cfg.source)()

    async def run(self):
        while True:
            try:
                tkr   = await self._ex.fetch_ticker(self.cfg.symbol)
                self.price = D.Decimal(str(tkr["last"]))
            except Exception as e:
                # 로깅 생략
                pass
            await asyncio.sleep(self.cfg.poll_sec)
