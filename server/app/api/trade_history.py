from fastapi import APIRouter, HTTPException, status

from app.database.trade_history import TradeHistory


router = APIRouter(
    prefix="/api/mt5/history",
    tags=["Trade History"],
)

trade_history = TradeHistory()

AI_MAGIC_NUMBER = 202609


def filter_ai_trades(trades):
    return [
        trade
        for trade in trades
        if trade.get("magic", AI_MAGIC_NUMBER) == AI_MAGIC_NUMBER
    ]


@router.get("")
def get_trade_history():
    try:
        trades = trade_history.get_all_trades()
        trades = filter_ai_trades(trades)

        return {
            "source": "AI Trading Platform Trade History",
            "magic": AI_MAGIC_NUMBER,
            "count": len(trades),
            "trades": trades,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to load trade history: {exc}",
        )


@router.get("/closed")
def get_closed_trade_history():
    try:
        trades = trade_history.get_closed_trades()
        trades = filter_ai_trades(trades)

        return {
            "source": "AI Trading Platform Trade History",
            "magic": AI_MAGIC_NUMBER,
            "count": len(trades),
            "trades": trades,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to load closed trade history: {exc}",
        )


@router.get("/open")
def get_open_trade_history():
    try:
        trades = trade_history.get_open_trades()
        trades = filter_ai_trades(trades)

        return {
            "source": "AI Trading Platform Trade History",
            "magic": AI_MAGIC_NUMBER,
            "count": len(trades),
            "trades": trades,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to load open trade history: {exc}",
        )


@router.get("/{ticket}")
def get_trade_history_by_ticket(ticket: int):
    try:
        trade = trade_history.get_trade_by_ticket(ticket)

        if trade is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trade {ticket} was not found",
            )

        if trade.get("magic", AI_MAGIC_NUMBER) != AI_MAGIC_NUMBER:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trade {ticket} was not found",
            )

        return {
            "source": "AI Trading Platform Trade History",
            "magic": AI_MAGIC_NUMBER,
            "trade": trade,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to load trade {ticket}: {exc}",
        )