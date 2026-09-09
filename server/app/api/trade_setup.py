from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.market_data import market_data_manager
from app.core.auth import get_current_user
from app.database.connection import get_db
from app.models.user import User
from app.services.trade_setup_service import (
    analyze_trade_setup,
    serialize_trade_setup,
)
from app.services.timeframe_service import TIMEFRAME_MINUTES


router = APIRouter(
    prefix="/api/analysis",
    tags=["Trade Setup"],
)


@router.get("/trade-setup/{symbol}/{timeframe}")
async def get_trade_setup(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    normalized_symbol = symbol.strip().upper()
    normalized_timeframe = timeframe.strip().lower()

    if normalized_timeframe not in TIMEFRAME_MINUTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported timeframe: "
                f"{normalized_timeframe}"
            ),
        )

    if limit < 20 or limit > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit must be between 20 and 1000",
        )

    price = market_data_manager.get_price(
        normalized_symbol
    )

    if price is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No live market price available for "
                f"{normalized_symbol}"
            ),
        )

    try:
        setup = analyze_trade_setup(
            db=db,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            current_price=Decimal(str(price)),
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return serialize_trade_setup(setup)