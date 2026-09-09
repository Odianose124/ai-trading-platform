from fastapi import APIRouter
from app.services.risk_gate import RiskGate


router = APIRouter(
    prefix="/risk",
    tags=["Risk Gate"]
)


risk_gate = RiskGate()


@router.post("/check")
def check_trade(trade: dict):

    result = risk_gate.evaluate(trade)

    return result