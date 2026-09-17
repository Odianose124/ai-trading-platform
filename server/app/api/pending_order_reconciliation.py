from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database.connection import get_db
from app.models.trade_intent import TradeIntent
from app.models.user import User
from app.services.pending_order_reconciliation_service import (
    pending_order_reconciliation_service,
)


router = APIRouter(
    prefix="/api/pending-orders",
    tags=["Pending Orders"],
)


@router.get("")
def list_pending_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    intents = (
        db.query(TradeIntent)
        .filter(
            TradeIntent.user_id == current_user.id,
            TradeIntent.execution_mode == "pending",
            TradeIntent.pending_order_status.in_(
                ["placed", "partial"]
            ),
            TradeIntent.order_ticket.isnot(None),
        )
        .order_by(
            TradeIntent.pending_order_placed_at.desc(),
            TradeIntent.id.desc(),
        )
        .all()
    )

    return {
        "count": len(intents),
        "pending_orders": [
            {
                "intent_id": intent.id,
                "symbol": intent.symbol,
                "broker_symbol": intent.broker_symbol,
                "direction": intent.direction,
                "order_type": intent.order_type,
                "execution_mode": intent.execution_mode,
                "volume": float(intent.volume),
                "entry_price": float(intent.signal_entry_price),
                "stop_loss": float(intent.stop_loss),
                "take_profit": float(intent.take_profit),
                "order_ticket": intent.order_ticket,
                "deal_ticket": intent.deal_ticket,
                "filled_position_ticket": intent.filled_position_ticket,
                "pending_order_status": intent.pending_order_status,
                "execution_status": intent.execution_status,
                "placed_at": (
                    intent.pending_order_placed_at.isoformat()
                    if intent.pending_order_placed_at
                    else None
                ),
                "created_at": (
                    intent.created_at.isoformat()
                    if intent.created_at
                    else None
                ),
                "updated_at": (
                    intent.updated_at.isoformat()
                    if intent.updated_at
                    else None
                ),
                "expires_at": (
                    intent.expires_at.isoformat()
                    if intent.expires_at
                    else None
                ),
            }
            for intent in intents
        ],
    }


@router.post("/{intent_id}/reconcile")
def reconcile_pending_order(
    intent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = pending_order_reconciliation_service.reconcile_intent(
        db,
        intent_id=intent_id,
        user_id=current_user.id,
    )

    if result.status == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.message,
        )

    return result.serialize()
