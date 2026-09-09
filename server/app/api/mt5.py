from fastapi import APIRouter, HTTPException, status

from app.mt5.connection import (
    MT5ConnectionError,
    mt5_connection,
)


router = APIRouter(
    prefix="/api/mt5",
    tags=["MetaTrader 5"],
)


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