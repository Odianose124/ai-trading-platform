from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.market_data import market_data_manager
from app.database.connection import get_db
from app.services.ai_market_analysis_service import (
    analyze_market,
    serialize_market_analysis,
)
from app.services.timeframe_service import TIMEFRAME_MINUTES


router = APIRouter(
    prefix="/api/analysis",
    tags=["AI Market Analysis"],
)


@router.get("/market/{symbol}/{timeframe}")
def get_market_analysis(
    symbol: str,
    timeframe: str,
    limit: int = 200,
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

    current_price = market_data_manager.get_price(
        normalized_symbol
    )

    if current_price is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No live market price available for "
                f"{normalized_symbol}"
            ),
        )

    current_price = Decimal(str(current_price))

    analysis = analyze_market(
        db=db,
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        current_price=current_price,
        limit=limit,
    )

    return serialize_market_analysis(analysis)