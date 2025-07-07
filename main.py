import asyncio, signal, logging, time
from core.models    import load_config
from core.feed      import UpbitFeed, BinanceFeed, BybitFeed
from core.exchange  import ExchWrapper
from core.strategy  import Strategy
from core.oms       import OMS
from dotenv         import dotenv_values

async def main():
    cfg = load_config()

    # --- 큐
    mkt_q, ord_q = asyncio.Queue(), asyncio.Queue()

    # --- WebSocket Feeds
    feeds = [
        UpbitFeed(mkt_q, cfg.exchanges['spot'].symbol.replace('/','-')),
        BinanceFeed(mkt_q, f"btcusdt@{cfg.exchanges['hedge_primary'].ws_stream}"),
    ]

    # --- Exchanges
    api_keys = dotenv_values(".env")            # .env에 exchange별 key/secret
    upbit  = ExchWrapper(**cfg.exchanges['spot'].dict())
    hedge  = ExchWrapper(**cfg.exchanges['hedge_primary'].dict())
    await asyncio.gather(upbit.init(api_keys), hedge.init(api_keys))

    # --- Modules
    strat = Strategy(cfg.strategy, mkt_q, ord_q)
    oms   = OMS(upbit, hedge, cfg.strategy, ord_q)

    # --- FX Poller
    fx  = FxPoller(cfg.fx)                 # cfg.fx 는 pydantic 객체
 
    # --- OMS (fx 주입)
    oms   = OMS(upbit, hedge, cfg.strategy, ord_q, fx)

    # --- Task gather
    tasks = [fx.run(), *(f.run() for f in feeds), strat.run(), oms.run()]

    loop_task = asyncio.gather(*tasks)
    # Graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_event_loop().add_signal_handler(sig, loop_task.cancel)
    await loop_task

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
