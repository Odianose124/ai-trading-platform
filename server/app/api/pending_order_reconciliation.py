from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database.connection import get_db
from app.models.user import User
from app.services.pending_order_reconciliation_service import (
    pending_order_reconciliation_service,
)


router = APIRouter(
    prefix="/api/pending-orders",
    tags=["Pending Orders"],
)


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
