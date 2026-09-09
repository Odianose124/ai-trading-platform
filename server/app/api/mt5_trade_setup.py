from fastapi import APIRouter, HTTPException, status

from app.mt5.connection import mt5_connection

from app.services.mt5_trade_setup_service import (
    MT5TradeSetupError,
    mt5_trade_setup_service,
)


router = APIRouter(
    prefix="/api/mt5",
    tags=["MT5 Trade Setup"],
)


def ensure_mt5_connection() -> None:

    if not mt5_connection.is_connected():

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MetaTrader 5 is not connected",
        )


@router.get(
    "/trade-setup/{symbol}"
)
def get_mt5_trade_setup(
    symbol: str,
    timeframe: str = "15m",
    limit: int = 500,
    strength: int = 2,
    lookback: int = 20,
    minimum_touches: int = 2,
):

    ensure_mt5_connection()

    try:

        setup = (
            mt5_trade_setup_service.analyze(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                strength=strength,
                lookback=lookback,
                minimum_touches=minimum_touches,
            )
        )

        return (
            mt5_trade_setup_service.serialize(
                setup
            )
        )

    except MT5TradeSetupError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )