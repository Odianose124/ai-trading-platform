from fastapi import APIRouter
from app.services.lot_calculator import LotCalculator


router = APIRouter(
    prefix="/lot",
    tags=["Lot Calculator"]
)


lot_calculator = LotCalculator()


@router.post("/calculate")
def calculate_lot(trade: dict):

    result = lot_calculator.calculate(
        balance=trade.get("balance"),
        risk_percent=trade.get("risk_percent"),
        entry_price=trade.get("entry_price"),
        stop_loss=trade.get("stop_loss"),
        symbol=trade.get(
            "symbol",
            "XAUUSDm"
        )
    )

    return result