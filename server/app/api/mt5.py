from fastapi import APIRouter, HTTPException, status

from app.execution.position_manager import PositionManager
from app.mt5.connection import (
    MT5ConnectionError,
    mt5_connection,
)


router = APIRouter(
    prefix="/api/mt5",
    tags=["MetaTrader 5"],
)

position_manager = PositionManager()


@router.post("/connect")
def connect_mt5():
    try:
        return mt5_connection.connect()

    except MT5ConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )


@router.get("/status")
def get_mt5_status():
    if not mt5_connection.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MetaTrader 5 is not connected",
        )

    try:
        return mt5_connection.get_status()

    except MT5ConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )


@router.post("/disconnect")
def disconnect_mt5():
    mt5_connection.disconnect()

    return {
        "connected": False,
        "message": "MetaTrader 5 connection closed",
    }


@router.get("/positions")
def get_mt5_positions(symbol: str | None = None):
    if not mt5_connection.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MetaTrader 5 is not connected",
        )

    try:
        positions = position_manager.get_positions(
            symbol=symbol
        )

        summary = position_manager.summary()

        return {
            "source": "MetaTrader 5",
            "magic": position_manager.magic_number,
            "count": len(positions),
            "positions": positions,
            "summary": summary,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to load MT5 positions: {exc}",
        )


@router.get("/positions/summary")
def get_mt5_positions_summary():
    if not mt5_connection.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MetaTrader 5 is not connected",
        )

    try:
        return {
            "source": "MetaTrader 5",
            "magic": position_manager.magic_number,
            **position_manager.summary(),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to load MT5 position summary: {exc}",
        )