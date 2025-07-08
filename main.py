import asyncio, signal, logging, time
from core.models    import load_config
from core.feed      import UpbitFeed, BinanceFeed, BybitFeed
from core.exchange  import ExchWrapper
from core.strategy  import Strategy
from core.oms       import OMS
from core.monitor import Monitor
from core.fx import FxPoller
from dotenv         import dotenv_values
from prometheus_client import start_http_server, Summary, Counter

# --- start Prometheus exporter (port 9100)
start_http_server(9100)

# ✨ NEW: 메트릭 정의
LOOP_LAT  = Summary("strategy_loop_ms", "Strategy loop latency")
ORDERS_C  = Counter("orders_total", "Spot limit orders", ['side'])

async def main():
    cfg = load_config()
    mode = cfg.runtime.run_mode.upper()

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
    strat = Strategy(cfg.strategy, mkt_q, ord_q, LOOP_LAT)   # ← ① 메트릭 주입
    oms   = OMS(upbit, hedge, cfg.strategy, ord_q, ORDERS_C, fx) # ← ② 메트릭 주입
    fx    = FxPoller(cfg.fx)

    # --- Heartbeat task
    monitor = Monitor(upbit, hedge, oms)

    tasks = [fx.run(), monitor.run(),
             *(f.run() for f in feeds),
             strat.run(), oms.run()]
 
    # --- OMS (fx 주입)
    oms   = OMS(                       # orders_counter, fx 모두 전달
    spot=upbit,
    hedge=hedge,
    cfg=cfg.strategy,
    ord_q=ord_q,
    orders_counter=ORDERS_C,
    fx=fx)

    monitor = Monitor(upbit, hedge, oms)
    # --- Task gather
    tasks = [fx.run(), *(f.run() for f in feeds), strat.run(), oms.run()]

    loop_task = asyncio.gather(*tasks)
    # Graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_event_loop().add_signal_handler(sig, loop_task.cancel)
    await loop_task

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,                      # INFO → DEBUG
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())