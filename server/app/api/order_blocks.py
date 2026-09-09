from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.services.candle_service import get_recent_candles
from app.services.order_block_service import (
    detect_order_blocks,
    serialize_order_blocks,
)
from app.services.timeframe_service import (
    TIMEFRAME_MINUTES,
    aggregate_candles,
)


router = APIRouter(
    prefix="/api/analysis",
    tags=["Order Block Analysis"],
)


@router.get("/order-blocks/{symbol}/{timeframe}")
def get_order_blocks(
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

    order_blocks = detect_order_blocks(
        candles=candles,
    )

    return {
        "symbol": normalized_symbol,
        "timeframe": normalized_timeframe,
        "candle_count": len(candles),
        "order_block_count": len(order_blocks),
        "active_order_block_count": sum(
            1 for block in order_blocks
            if not block.mitigated
        ),
        "mitigated_order_block_count": sum(
            1 for block in order_blocks
            if block.mitigated
        ),
        "order_blocks": serialize_order_blocks(
            order_blocks
        ),
    }