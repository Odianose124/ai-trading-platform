from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.services.historical_data_service import (
    SYMBOL_MAPPING,
    backfill_symbol,
    backfill_symbols,
)


router = APIRouter(
    prefix="/api/market-data",
    tags=["Historical Market Data"],
)


@router.post("/backfill/{symbol}")
async def backfill_market_data(
    symbol: str,
    hours: int = Query(
        default=72,
        ge=1,
        le=168,
    ),
    db: Session = Depends(get_db),
):
    normalized_symbol = symbol.strip().upper()

    if normalized_symbol not in SYMBOL_MAPPING:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported symbol. "
                f"Supported symbols: "
                f"{', '.join(SYMBOL_MAPPING.keys())}"
            ),
        )

    try:
        result = await backfill_symbol(
            db=db,
            symbol=normalized_symbol,
            hours=hours,
        )

        return {
            "message": "Historical market data backfill completed",
            "result": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Historical market data backfill failed: {exc}",
        )


@router.post("/backfill")
async def backfill_all_market_data(
    hours: int = Query(
        default=72,
        ge=1,
        le=168,
    ),
    db: Session = Depends(get_db),
):
    symbols = list(SYMBOL_MAPPING.keys())

    try:
        results = await backfill_symbols(
            db=db,
            symbols=symbols,
            hours=hours,
        )

        return {
            "message": "Historical market data backfill completed",
            "symbols": symbols,
            "requested_hours": hours,
            "results": results,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Historical market data backfill failed: {exc}",
        )