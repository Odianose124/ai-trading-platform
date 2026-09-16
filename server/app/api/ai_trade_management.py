from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user
from app.database.connection import get_db
from app.services.ai_trade_management_orchestration_service import (
    AITradeManagementOrchestrationError,
    ai_trade_management_orchestration_service,
)

from app.services.ai_trade_management_service import (
    AITradeManagementError,
    ai_trade_management_service,
)


router = APIRouter(
    prefix="/api/ai-trade-management",
    tags=["AI Trade Management"],
)


@router.get(
    "/positions/{position_ticket}/evaluate",
)
def evaluate_position_management(
    position_ticket: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Read-only AI trade-management evaluation.

    This endpoint MUST NOT:
    - send an MT5 order
    - modify stop loss
    - modify take profit
    - close a position
    - change position volume
    - mutate the management profile

    It only evaluates the current live position against the
    immutable management profile.
    """

    try:
        result = ai_trade_management_service.evaluate(
            db=db,
            user_id=current_user.id,
            position_ticket=position_ticket,
        )

        return result.serialize()

    except AITradeManagementError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

 
@router.post(
    "/positions/{position_ticket}/execute",
)
def execute_position_management(
    position_ticket: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Controlled AI management execution.

    The service performs a fresh evaluation immediately before
    execution and sends only the evaluator-approved management
    decision to MT5.
    """

    try:
        return ai_trade_management_orchestration_service.execute(
            db=db,
            user_id=current_user.id,
            position_ticket=position_ticket,
        )

    except AITradeManagementOrchestrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
