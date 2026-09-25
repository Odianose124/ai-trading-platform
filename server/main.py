from contextlib import asynccontextmanager
import asyncio
from datetime import datetime, timezone

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings


from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models.mt5_trading_account import MT5TradingAccount
from app.models.user import User
from app.mt5.worker_manager import (
    MT5WorkerManagerError,
    mt5_worker_manager,
)
from app.api.auth import router as auth_router
from app.api.mt5 import router as mt5_router
from app.api.mt5_market_data import router as mt5_market_data_router
from app.api.mt5_multi_timeframe import router as mt5_multi_timeframe_router
from app.api.mt5_trade_setup import (
    router as mt5_trade_setup_router,
)
from app.api.trade_history import (
    router as trade_history_router,
)

from app.api.settings import router as settings_router

from app.routes import risk
from app.routes import lot

from app.api.execution_preview import (
    router as execution_preview_router,
)

from app.api.trade_intent import (
    router as trade_intent_router,
)

from app.api.trade_confirmation import (
    router as trade_confirmation_router,
)

from app.api.revalidation_intent import (
    router as revalidation_intent_router,
)

from app.api.trading import (
    router as trading_router,
)

from app.api.transactions import (
    router as transactions_router,
)

from app.api.market_data import (
    router as market_data_router,
    market_data_manager,
    live_order_monitor,
)

from app.database.connection import (
    create_database_tables,
)

from app.models.candle import Candle

from app.api.candles import (
    router as candles_router,
)

from app.api.analysis import (
    router as analysis_router,
)

from app.api.liquidity import (
    router as liquidity_router,
)

from app.api.fvg import (
    router as fvg_router,
)

from app.api.order_blocks import (
    router as order_blocks_router,
)

from app.api.support_resistance import (
    router as support_resistance_router,
)

from app.api.historical_data import (
    router as historical_data_router,
)

from app.api.ai_analysis import (
    router as ai_analysis_router,
)

from app.api.ai_signal import (
    router as ai_signal_router,
)

from app.api.multi_timeframe import (
    router as multi_timeframe_router,
)

from app.api.trade_setup import (
    router as trade_setup_router,
)

from app.api.risk_management import (
    router as risk_management_router,
)


from app.api.execution import (
    router as execution_router,
)

from app.api.ai_trade_management import (
    router as ai_trade_management_router,
)

from app.api.pending_order_reconciliation import (
    router as pending_order_reconciliation_router,
)

from app.services.pending_order_monitor import (
    pending_order_monitor,
)

from app.websocket.mt5_stream import (
    mt5_stream_service,
)

from app.websocket.manager import (
    websocket_manager,
)

def build_mt5_realtime_snapshot(
    mt5_account_id: int,
    user_id: int,
) -> dict:
    """
    Build one account-scoped realtime MT5 dashboard snapshot.

    All broker data is obtained through the dedicated account worker.
    """

    status_data = mt5_worker_manager.status_for_account(
        mt5_account_id=mt5_account_id,
        user_id=user_id,
    )

    account = mt5_worker_manager.account_info(
        mt5_account_id=mt5_account_id,
        user_id=user_id,
    )

    positions = mt5_worker_manager.get_positions(
        mt5_account_id=mt5_account_id,
        user_id=user_id,
    )

    pending_orders = mt5_worker_manager.get_pending_orders(
        mt5_account_id=mt5_account_id,
        user_id=user_id,
    )

    total_volume = sum(
        float(position.get("volume", 0) or 0)
        for position in positions
    )

    total_profit = sum(
        float(position.get("profit", 0) or 0)
        for position in positions
    )

    buy_positions = sum(
        1
        for position in positions
        if position.get("type") == "buy"
    )

    sell_positions = sum(
        1
        for position in positions
        if position.get("type") == "sell"
    )

    symbols = {
        str(position.get("symbol")).strip().upper()
        for position in positions
        if position.get("symbol")
    }

    symbols.update(
        str(order.get("symbol")).strip().upper()
        for order in pending_orders
        if order.get("symbol")
    )

    ticks: dict[str, dict] = {}

    for symbol in sorted(symbols):
        tick = mt5_worker_manager.symbol_info_tick(
            mt5_account_id=mt5_account_id,
            user_id=user_id,
            symbol=symbol,
        )

        ticks[symbol] = tick

    return {
        "type": "mt5_snapshot",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mt5_account_id": mt5_account_id,
        "user_id": user_id,
        "connection": status_data,
        "account": account,
        "positions": positions,
        "pending_orders": pending_orders,
        "summary": {
            "total_positions": len(positions),
            "buy_positions": buy_positions,
            "sell_positions": sell_positions,
            "total_volume": total_volume,
            "floating_profit": total_profit,
        },
        "ticks": ticks,
    }

MARKET_SYMBOLS = [
    "BTCUSD",
    "ETHUSD",
    "BNBUSD",
    "SOLUSD",
    "XRPUSD",
]



mt5_realtime_publisher_task = None
mt5_stream_task = None


async def mt5_realtime_publisher():

    while True:

        db = SessionLocal()

        try:

            accounts = (
                db.query(MT5TradingAccount)
                .filter(
                    MT5TradingAccount.is_active.is_(True)
                )
                .all()
            )

            for account in accounts:

                try:

                    snapshot = await asyncio.to_thread(
                        build_mt5_realtime_snapshot,
                        account.id,
                        account.user_id,
                    )

                    await mt5_stream_service.publish_snapshot(
                        user_id=account.user_id,
                        snapshot=snapshot,
                    )

                except Exception:
                    continue

        finally:
            db.close()

        await asyncio.sleep(1)


async def lifespan(app: FastAPI):

    create_database_tables()

    await market_data_manager.start_background(
        MARKET_SYMBOLS
    )

    await live_order_monitor.start_background()

    await pending_order_monitor.start_background()


    global mt5_realtime_publisher_task

    global mt5_stream_task

    mt5_stream_task = asyncio.create_task(
        mt5_stream_service.start()
    )

    mt5_realtime_publisher_task

    mt5_realtime_publisher_task = asyncio.create_task(
        mt5_realtime_publisher()
    )


    yield


    await pending_order_monitor.stop()

    await live_order_monitor.stop()

    await market_data_manager.stop()


    if mt5_realtime_publisher_task:
        mt5_realtime_publisher_task.cancel()

    try:
        if mt5_realtime_publisher_task:
            await mt5_realtime_publisher_task
    except asyncio.CancelledError:
        pass


    await mt5_stream_service.stop()

    if mt5_stream_task:
        try:
            await mt5_stream_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend API for the AI Trading Platform",
    lifespan=lifespan,
)

@app.websocket("/ws/mt5")
async def mt5_realtime_websocket(
    websocket: WebSocket,
    token: str | None = None,
):
    db: Session | None = None
    user_id: int | None = None

    try:
        if not token:
            await websocket.accept()

            await websocket.send_json(
                {
                    "type": "mt5_error",
                    "detail": "Authentication token is required.",
                }
            )

            await websocket.close(code=1008)
            return

        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )

            user_id_raw = payload.get("sub")

            if user_id_raw is None:
                raise ValueError("Missing user identity.")

            user_id = int(user_id_raw)

        except (JWTError, ValueError, TypeError):
            await websocket.accept()

            await websocket.send_json(
                {
                    "type": "mt5_error",
                    "detail": "Could not validate credentials.",
                }
            )

            await websocket.close(code=1008)
            return

        db = SessionLocal()

        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if user is None or not user.is_active:
            await websocket.accept()

            await websocket.send_json(
                {
                    "type": "mt5_error",
                    "detail": "User account is inactive or unavailable.",
                }
            )

            await websocket.close(code=1008)
            return

        account = (
            db.query(MT5TradingAccount)
            .filter(
                MT5TradingAccount.user_id == user_id,
                MT5TradingAccount.is_active.is_(True),
            )
            .first()
        )

        if account is None:
            await websocket.accept()

            await websocket.send_json(
                {
                    "type": "mt5_error",
                    "detail": (
                        "No active MT5 trading account is registered "
                        "for this user."
                    ),
                }
            )

            await websocket.close(code=1008)
            return

        await websocket_manager.connect(
            websocket=websocket,
            user_id=user_id,
        )

        while True:
            await asyncio.sleep(3600)

    except WebSocketDisconnect:
        pass

    finally:
        if user_id is not None:
            await websocket_manager.disconnect(
                websocket=websocket,
                user_id=user_id,
            )

        if db is not None:
            db.close()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)

app.include_router(mt5_router)

app.include_router(mt5_market_data_router)

app.include_router(
    mt5_multi_timeframe_router
)

app.include_router(
    mt5_trade_setup_router
)

app.include_router(
    trade_history_router
)

app.include_router(settings_router)

app.include_router(risk.router)

app.include_router(lot.router)

app.include_router(
    execution_preview_router
)

app.include_router(
    trade_intent_router
)

app.include_router(
    trade_confirmation_router
)

app.include_router(
    revalidation_intent_router
)

app.include_router(
    trading_router
)

app.include_router(
    transactions_router
)

app.include_router(
    market_data_router
)

app.include_router(
    candles_router
)

app.include_router(
    analysis_router
)

app.include_router(
    liquidity_router
)

app.include_router(
    fvg_router
)

app.include_router(
    order_blocks_router
)

app.include_router(
    support_resistance_router
)

app.include_router(
    historical_data_router
)

app.include_router(
    ai_analysis_router
)

app.include_router(
    ai_signal_router
)

app.include_router(
    multi_timeframe_router
)

app.include_router(
    trade_setup_router
)

app.include_router(
    risk_management_router
)

app.include_router(
    execution_router
)

app.include_router(
    ai_trade_management_router
)

app.include_router(
    pending_order_reconciliation_router
)


@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "AI Trading Platform API is running",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "AI Trading Platform API",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }











