from fastapi import APIRouter
from app.execution.mt5_executor import MT5Executor


router = APIRouter(
    prefix="/execution",
    tags=["MT5 Execution"]
)


executor = MT5Executor()


@router.post("/trade")
def execute_trade(trade: dict):

    result = executor.execute_trade(
        symbol=trade["symbol"],
        direction=trade["direction"],
        volume=trade["lot_size"],
        stop_loss=trade["stop_loss"],
        take_profit=trade["take_profit"]
    )

    return result