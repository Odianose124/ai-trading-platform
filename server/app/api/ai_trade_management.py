from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database.connection import get_db
from app.models.ai_management_action import AIManagementAction
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
    db: Session = Depends(get_db),
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
    db: Session = Depends(get_db),
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


@router.get(
    "/positions/{position_ticket}/actions",
)
def get_position_management_actions(
    position_ticket: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return the persisted AI management action history for one
    position belonging to the authenticated user.

    This endpoint is read-only and never communicates with MT5.
    """

    actions = (
        db.query(AIManagementAction)
        .filter(
            AIManagementAction.user_id == current_user.id,
            AIManagementAction.position_ticket == position_ticket,
        )
        .order_by(
            AIManagementAction.created_at.desc(),
            AIManagementAction.id.desc(),
        )
        .all()
    )

    return {
        "position_ticket": position_ticket,
        "count": len(actions),
        "actions": [
            {
                "id": action.id,
                "user_id": action.user_id,
                "mt5_account_id": action.mt5_account_id,
                "managed_position_id": action.managed_position_id,
                "position_ticket": action.position_ticket,
                "decision": action.decision,
                "action_key": action.action_key,
                "status": action.status,
                "requested_volume": (
                    float(action.requested_volume)
                    if action.requested_volume is not None
                    else None
                ),
                "requested_stop_loss": (
                    float(action.requested_stop_loss)
                    if action.requested_stop_loss is not None
                    else None
                ),
                "partial_close_percent": (
                    float(action.partial_close_percent)
                    if action.partial_close_percent is not None
                    else None
                ),
                "retcode": action.retcode,
                "retcode_description": action.retcode_description,
                "message": action.message,
                "created_at": (
                    action.created_at.isoformat()
                    if action.created_at is not None
                    else None
                ),
                "updated_at": (
                    action.updated_at.isoformat()
                    if action.updated_at is not None
                    else None
                ),
            }
            for action in actions
        ],
    }


@router.get(
    "/actions/{action_id}",
)
def get_management_action(
    action_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return one persisted AI management action belonging to the
    authenticated user.

    This endpoint is read-only and never communicates with MT5.
    """

    action = (
        db.query(AIManagementAction)
        .filter(
            AIManagementAction.id == action_id,
            AIManagementAction.user_id == current_user.id,
        )
        .first()
    )

    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI management action was not found.",
        )

    return {
        "id": action.id,
        "user_id": action.user_id,
        "mt5_account_id": action.mt5_account_id,
        "managed_position_id": action.managed_position_id,
        "position_ticket": action.position_ticket,
        "decision": action.decision,
        "action_key": action.action_key,
        "status": action.status,
        "requested_volume": (
            float(action.requested_volume)
            if action.requested_volume is not None
            else None
        ),
        "requested_stop_loss": (
            float(action.requested_stop_loss)
            if action.requested_stop_loss is not None
            else None
        ),
        "partial_close_percent": (
            float(action.partial_close_percent)
            if action.partial_close_percent is not None
            else None
        ),
        "retcode": action.retcode,
        "retcode_description": action.retcode_description,
        "message": action.message,
        "created_at": (
            action.created_at.isoformat()
            if action.created_at is not None
            else None
        ),
        "updated_at": (
            action.updated_at.isoformat()
            if action.updated_at is not None
            else None
        ),
    }