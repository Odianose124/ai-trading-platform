from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.services.timeframe_service import (
    TIMEFRAME_MINUTES,
    aggregate_candles,
)


router = APIRouter(
    prefix="/api/candles",
    tags=["Candles"],
)


@router.get("/{symbol}/{timeframe}")
def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 100,
    db: Session = Depends(get_db),
):

    normalized_symbol = symbol.strip().upper()
    normalized_timeframe = (
        timeframe.strip().lower()
    )

    if normalized_timeframe not in TIMEFRAME_MINUTES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported timeframe. "
                f"Supported timeframes: "
                f"{', '.join(TIMEFRAME_MINUTES.keys())}"
            ),
        )

    if limit < 1 or limit > 1000:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 1000",
        )

    try:

        candles = aggregate_candles(
            db=db,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            limit=limit,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    return {
        "symbol": normalized_symbol,
        "timeframe": normalized_timeframe,
        "count": len(candles),
        "candles": [
            {
                "open_time": candle.open_time,
                "close_time": candle.close_time,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "trade_count": candle.trade_count,
            }
            for candle in candles
        ],
    }