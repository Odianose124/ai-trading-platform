from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings

from app.api.auth import router as auth_router
from app.api.mt5 import router as mt5_router
from app.api.mt5_market_data import router as mt5_market_data_router
from app.api.mt5_multi_timeframe import router as mt5_multi_timeframe_router
from app.api.mt5_trade_setup import (
    router as mt5_trade_setup_router,
)
from app.routes import risk
from app.routes import lot
from app.routes import execution
from app.api.execution_preview import router as execution_preview_router
from app.api.trade_intent import router as trade_intent_router
from app.api.trade_confirmation import router as trade_confirmation_router
from app.api.revalidation_intent import (
    router as revalidation_intent_router,
)
from app.api.trading import router as trading_router
from app.api.transactions import router as transactions_router
from app.api.market_data import (
    router as market_data_router,
    market_data_manager,
    live_order_monitor,
)
from app.database.connection import create_database_tables
from app.models.candle import Candle
from app.api.candles import router as candles_router
from app.api.analysis import router as analysis_router
from app.api.liquidity import router as liquidity_router
from app.api.fvg import router as fvg_router
from app.api.order_blocks import router as order_blocks_router
from app.api.support_resistance import router as support_resistance_router
from app.api.historical_data import router as historical_data_router
from app.api.ai_analysis import router as ai_analysis_router
from app.api.ai_signal import router as ai_signal_router
from app.api.multi_timeframe import router as multi_timeframe_router
from app.api.trade_setup import router as trade_setup_router
from app.api.risk_management import router as risk_management_router
from app.api.execution import router as execution_router


MARKET_SYMBOLS = [
    "BTCUSD",
    "ETHUSD",
    "BNBUSD",
    "SOLUSD",
    "XRPUSD",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Make sure all database tables exist before
    # starting live market-data and trading services.
    create_database_tables()

    # Start live market-data collection.
    await market_data_manager.start_background(
        MARKET_SYMBOLS
    )

    # Start automatic SL/TP order monitoring.
    await live_order_monitor.start_background()

    yield

    # Stop the live order monitor.
    await live_order_monitor.stop()

    # Stop the market-data connection.
    await market_data_manager.stop()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend API for the AI Trading Platform",
    lifespan=lifespan,
)

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

app.include_router(risk.router)

app.include_router(lot.router)

app.include_router(execution.router)

app.include_router(execution_preview_router)

app.include_router(trade_intent_router)

app.include_router(trade_confirmation_router)

app.include_router(revalidation_intent_router)

app.include_router(trading_router)

app.include_router(transactions_router)

app.include_router(market_data_router)

app.include_router(candles_router)

app.include_router(analysis_router)

app.include_router(liquidity_router)

app.include_router(fvg_router)

app.include_router(order_blocks_router)

app.include_router(support_resistance_router)

app.include_router(historical_data_router)

app.include_router(ai_analysis_router)

app.include_router(ai_signal_router)

app.include_router(multi_timeframe_router)

app.include_router(trade_setup_router)

app.include_router(risk_management_router)

app.include_router(execution_router)


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