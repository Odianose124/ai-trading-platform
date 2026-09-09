from fastapi import APIRouter, HTTPException, status

from app.mt5.connection import mt5_connection

from app.services.mt5_multi_timeframe_service import (
    MT5MultiTimeframeAnalysisError,
    mt5_multi_timeframe_service,
)


router = APIRouter(
    prefix="/api/mt5",
    tags=["MT5 Multi-Timeframe AI"],
)


def ensure_mt5_connection() -> None:
    if not mt5_connection.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MetaTrader 5 is not connected",
        )


@router.get(
    "/analysis/multi-timeframe/{symbol}"
)
def get_mt5_multi_timeframe_analysis(
    symbol: str,
    primary_timeframe: str = "15m",
    limit: int = 500,
    strength: int = 2,
    lookback: int = 20,
    minimum_touches: int = 2,
):
    ensure_mt5_connection()

    try:
        analysis = (
            mt5_multi_timeframe_service.analyze(
                symbol=symbol,
                primary_timeframe=primary_timeframe,
                limit=limit,
                strength=strength,
                lookback=lookback,
                minimum_touches=minimum_touches,
            )
        )

        return (
            mt5_multi_timeframe_service.serialize(
                analysis
            )
        )

    except MT5MultiTimeframeAnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )