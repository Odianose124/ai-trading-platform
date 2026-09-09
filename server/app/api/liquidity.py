from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.services.candle_service import get_recent_candles
from app.services.liquidity_service import (
    detect_liquidity_sweeps,
    serialize_liquidity_sweeps,
)
from app.services.timeframe_service import (
    TIMEFRAME_MINUTES,
    aggregate_candles,
)


router = APIRouter(
    prefix="/api/analysis",
    tags=["Liquidity Analysis"],
)


@router.get("/liquidity/{symbol}/{timeframe}")
def get_liquidity_sweeps(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    strength: int = 2,
    db: Session = Depends(get_db),
):
    normalized_symbol = symbol.strip().upper()
    normalized_timeframe = timeframe.strip().lower()

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

    if strength < 1 or strength > 10:
        raise HTTPException(
            status_code=400,
            detail="Strength must be between 1 and 10",
        )

    if normalized_timeframe == "1m":
        candles = get_recent_candles(
            db=db,
            symbol=normalized_symbol,
            timeframe="1m",
            limit=limit,
        )
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

    sweeps = detect_liquidity_sweeps(
        candles=candles,
        strength=strength,
    )

    return {
        "symbol": normalized_symbol,
        "timeframe": normalized_timeframe,
        "candle_count": len(candles),
        "swing_strength": strength,
        "sweep_count": len(sweeps),
        "liquidity_sweeps": serialize_liquidity_sweeps(sweeps),
    }