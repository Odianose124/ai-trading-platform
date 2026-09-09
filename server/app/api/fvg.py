from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.services.candle_service import get_recent_candles
from app.services.fvg_service import (
    detect_fair_value_gaps,
    serialize_fair_value_gaps,
)
from app.services.timeframe_service import (
    TIMEFRAME_MINUTES,
    aggregate_candles,
)


router = APIRouter(
    prefix="/api/analysis",
    tags=["FVG Analysis"],
)


@router.get("/fvg/{symbol}/{timeframe}")
def get_fair_value_gaps(
    symbol: str,
    timeframe: str,
    limit: int = 200,
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

    gaps = detect_fair_value_gaps(candles)

    return {
        "symbol": normalized_symbol,
        "timeframe": normalized_timeframe,
        "candle_count": len(candles),
        "fvg_count": len(gaps),
        "active_fvg_count": sum(
            1 for gap in gaps if not gap.mitigated
        ),
        "mitigated_fvg_count": sum(
            1 for gap in gaps if gap.mitigated
        ),
        "fair_value_gaps": serialize_fair_value_gaps(gaps),
    }