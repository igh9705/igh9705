import asyncio, signal, logging, time

from dotenv         import dotenv_values
from prometheus_client import start_http_server, Summary, Counter

from core.models    import load_config
from core.feed      import UpbitFeed, BinanceFeed
from core.exchange  import ExchWrapper
from core.strategy  import Strategy
from core.oms       import OMS
from core.fx        import FxPoller
from core.monitor   import Monitor
from core.order_poller import UpbitOrderPoller

async def main() -> None:
    # ─────────────────────────── 설정 로드
    cfg = load_config()                    # 반드시 runtime.run_mode: LIVE 로 되어 있어야 함

    # ─────────────────────────── Prometheus
    start_http_server(9100)
    LOOP_LAT = Summary("strategy_loop_ms", "Strategy loop latency (ms)")
    ORDERS_C = Counter("orders_total", "Spot limit‑주문 건수", ['side'])

    # ─────────────────────────── 큐
    mkt_q, ord_q, fill_q = asyncio.Queue(), asyncio.Queue(), asyncio.Queue()

    # ─────────────────────────── WebSocket 피드
    feeds = [
    UpbitFeed(mkt_q, symbol="USDT-BTC"),          # 현물
    BinanceFeed(mkt_q, stream="btcusdt@bookTicker")]  # 선물

    # ─────────────────────────── REST 거래소 초기화
    keys = dotenv_values(".env")  # .env 에 UPBIT_KEY=…, BINANCEUSDM_KEY=…  형식
    upbit  = ExchWrapper(**cfg.exchanges['spot'].dict())
    hedge  = ExchWrapper(**cfg.exchanges['hedge_primary'].dict())
    await asyncio.gather(upbit.init(keys), hedge.init(keys))

    # ─────────────────────────── FX Poller (USDT/KRW 환율)
    fx = FxPoller(cfg.fx)

    # ─────────────────────────── 핵심 모듈
    strat = Strategy(
        cfg.strategy,
        mkt_q, ord_q,
        LOOP_LAT,
        cfg.runtime.loop_ms
    )
    oms   = OMS(
        spot=upbit,
        hedge=hedge,
        cfg=cfg.strategy,
        ord_q=ord_q,
        fill_q = fill_q,
        orders_counter=ORDERS_C,
        fx=fx
    )
    poller = UpbitOrderPoller(upbit, oms.watch_set, fill_q, poll_ms=1000)

    monitor = Monitor(upbit, hedge, oms)

    # ─────────────────────────── Task 묶음
    tasks = [
        fx.run(),
        monitor.run(),
        poller.run(),
        *(f.run() for f in feeds),
        strat.run(),
        oms.run()
    ]

    # ─────────────────────────── Graceful Shutdown
    loop_task = asyncio.gather(*tasks)
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, loop_task.cancel)

    try:
        await loop_task
    finally:
        if hasattr(upbit, "ccxt_ex"):
            await upbit.ccxt_ex.close()
        if hasattr(hedge, "ccxt_ex"):
            await hedge.ccxt_ex.close()



# ─────────────────────────── 실행 진입점
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asc" \
        "time)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("ccxt.base.exchange").setLevel(logging.INFO)

    asyncio.run(main())
