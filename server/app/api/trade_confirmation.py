from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database.connection import get_db
from app.services.trade_confirmation_service import (
    trade_confirmation_service,
)


router = APIRouter(
    prefix="/api/trade-confirmation",
    tags=["Trade Confirmation"],
)


class ConfirmTradeRequest(BaseModel):
    intent_id: int = Field(gt=0)


@router.post("")
def confirm_trade(
    request: ConfirmTradeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = trade_confirmation_service.confirm(
        db,
        intent_id=request.intent_id,
        user_id=current_user.id,
    )

    return result.serialize()
