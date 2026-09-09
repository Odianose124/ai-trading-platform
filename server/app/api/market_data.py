from fastapi import APIRouter, HTTPException

from app.market_data.manager import MarketDataManager
from app.market_data.order_monitor import LiveOrderMonitor


router = APIRouter(
    prefix="/api/market-data",
    tags=["Market Data"],
)


market_data_manager = MarketDataManager()


MARKET_SYMBOLS = [
    "BTCUSD",
    "ETHUSD",
    "BNBUSD",
    "SOLUSD",
    "XRPUSD",
]


live_order_monitor = LiveOrderMonitor(
    market_data_manager=market_data_manager,
    symbols=MARKET_SYMBOLS,
    interval_seconds=0.25,
)


@router.get("/price/{symbol}")
async def get_market_price(symbol: str):
    price = market_data_manager.get_price(symbol)

    if price is None:
        raise HTTPException(
            status_code=404,
            detail=f"No live market price available for {symbol.upper()}",
        )

    updated_at = market_data_manager.get_price_updated_at(
        symbol
    )

    return {
        "symbol": symbol.upper(),
        "price": price,
        "updated_at": updated_at,
        "source": "Binance",
    }


@router.get("/prices")
async def get_market_prices():
    prices = market_data_manager.get_all_prices()

    return {
        "source": "Binance",
        "prices": prices,
    }