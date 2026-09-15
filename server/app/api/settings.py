from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database.connection import get_db
from app.models.user import User
from app.models.user_settings import UserSettings


router = APIRouter(
    prefix="/api/settings",
    tags=["Settings"],
)


class SettingsResponse(BaseModel):
    risk_percent: float
    max_risk_percent: float
    preferred_timeframe: str
    max_open_trades: int
    auto_trading_enabled: bool
    require_trade_confirmation: bool


class SettingsUpdate(BaseModel):
    risk_percent: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
    )

    max_risk_percent: float = Field(
        default=2.0,
        ge=0.1,
        le=20.0,
    )

    preferred_timeframe: str = Field(
        default="15m",
        min_length=1,
        max_length=20,
    )

    max_open_trades: int = Field(
        default=3,
        ge=1,
        le=20,
    )

    auto_trading_enabled: bool = False

    require_trade_confirmation: bool = True


ALLOWED_TIMEFRAMES = {
    "1m",
    "5m",
    "15m",
    "1h",
    "4h",
}


def serialize_settings(settings: UserSettings):
    return {
        "risk_percent": settings.risk_percent,
        "max_risk_percent": settings.max_risk_percent,
        "preferred_timeframe": settings.preferred_timeframe,
        "max_open_trades": settings.max_open_trades,
        "auto_trading_enabled": settings.auto_trading_enabled,
        "require_trade_confirmation": settings.require_trade_confirmation,
    }


def get_or_create_settings(
    db: Session,
    user: User,
):
    settings = (
        db.query(UserSettings)
        .filter(UserSettings.user_id == user.id)
        .first()
    )

    if settings is None:
        settings = UserSettings(
            user_id=user.id,
        )

        db.add(settings)
        db.commit()
        db.refresh(settings)

    return settings


@router.get(
    "",
    response_model=SettingsResponse,
)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_or_create_settings(
        db,
        current_user,
    )

    return serialize_settings(settings)


@router.put(
    "",
    response_model=SettingsResponse,
)
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if (
        payload.preferred_timeframe
        not in ALLOWED_TIMEFRAMES
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid timeframe. Allowed values: "
                "1m, 5m, 15m, 1h, 4h."
            ),
        )

    if (
        payload.max_risk_percent
        < payload.risk_percent
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Maximum risk percent cannot be "
                "lower than the default risk percent."
            ),
        )

    settings = get_or_create_settings(
        db,
        current_user,
    )

    settings.risk_percent = payload.risk_percent
    settings.max_risk_percent = (
        payload.max_risk_percent
    )
    settings.preferred_timeframe = (
        payload.preferred_timeframe
    )
    settings.max_open_trades = (
        payload.max_open_trades
    )
    settings.auto_trading_enabled = (
        payload.auto_trading_enabled
    )
    settings.require_trade_confirmation = (
        payload.require_trade_confirmation
    )
    settings.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(settings)

    return serialize_settings(settings)
