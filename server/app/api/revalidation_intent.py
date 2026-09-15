from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database.connection import get_db
from app.services.revalidation_intent_service import (
    revalidation_intent_service,
)

router = APIRouter(
    prefix="/api/revalidation-intent",
    tags=["Revalidation Intent"],
)


class RevalidationIntentRequest(BaseModel):
    intent_id: int = Field(gt=0)


@router.post("")
def revalidate_trade_intent(
    request: RevalidationIntentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = revalidation_intent_service.revalidate_and_create(
        db=db,
        intent_id=request.intent_id,
        user_id=current_user.id,
    )

    return result.serialize()
