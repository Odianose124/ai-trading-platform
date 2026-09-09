from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.market_data import market_data_manager
from app.database.connection import get_db
from app.services.candle_service import get_recent_candles
from app.services.support_resistance_service import (
    detect_support_resistance,
    get_nearest_resistance,
    get_nearest_support,
    serialize_levels,
)
from app.services.timeframe_service import (
    TIMEFRAME_MINUTES,
    aggregate_candles,
)


router = APIRouter(
    prefix="/api/analysis",
    tags=["Support & Resistance"],
)


@router.get("/support-resistance/{symbol}/{timeframe}")
def get_support_resistance(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    minimum_touches: int = 2,
    db: Session = Depends(get_db),
):
    normalized_symbol = symbol.strip().upper()
    normalized_timeframe = timeframe.strip().lower()

    if not normalized_symbol:
        raise HTTPException(
            status_code=400,
            detail="Symbol is required",
        )

    if normalized_timeframe not in TIMEFRAME_MINUTES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported timeframe. "
                f"Supported timeframes: "
                f"{', '.join(TIMEFRAME_MINUTES.keys())}"
            ),
        )

    if limit < 20 or limit > 1000:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 20 and 1000",
        )

    if minimum_touches < 1 or minimum_touches > 10:
        raise HTTPException(
            status_code=400,
            detail="Minimum touches must be between 1 and 10",
        )

    # 1-minute candles are already stored directly.
    if normalized_timeframe == "1m":
        candles = get_recent_candles(
            db=db,
            symbol=normalized_symbol,
            timeframe="1m",
            limit=limit,
        )

    # Higher timeframes are built from the real stored 1-minute candles.
    else:
        candles = aggregate_candles(
            db=db,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            limit=limit,
        )

    if not candles:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No candle data available for "
                f"{normalized_symbol} {normalized_timeframe}"
            ),
        )

    # Use the existing live market-data manager.
    # This ensures Support & Resistance uses the same
    # live price cache as the rest of the application.
    current_price = market_data_manager.get_price(
        normalized_symbol
    )

    # If a live price is temporarily unavailable,
    # use the close of the latest available candle.
    if current_price is None:
        current_price = candles[-1].close

    current_price = Decimal(str(current_price))

    levels = detect_support_resistance(
        candles=candles,
        current_price=current_price,
        minimum_touches=minimum_touches,
    )

    nearest_support = get_nearest_support(
        levels=levels,
        current_price=current_price,
    )

    nearest_resistance = get_nearest_resistance(
        levels=levels,
        current_price=current_price,
    )

    serialized_levels = serialize_levels(levels)

    return {
        "symbol": normalized_symbol,
        "timeframe": normalized_timeframe,
        "candle_count": len(candles),
        "current_price": current_price,
        "level_count": len(levels),
        "support_count": sum(
            1
            for level in levels
            if level.type == "support"
        ),
        "resistance_count": sum(
            1
            for level in levels
            if level.type == "resistance"
        ),
        "nearest_support": (
            serialize_levels([nearest_support])[0]
            if nearest_support
            else None
        ),
        "nearest_resistance": (
            serialize_levels([nearest_resistance])[0]
            if nearest_resistance
            else None
        ),
        "levels": serialized_levels,
    }