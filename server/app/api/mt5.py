from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database.connection import get_db
from app.execution.position_manager import PositionManager
from app.models.mt5_trading_account import MT5TradingAccount
from app.models.user import User
from app.mt5.connection import (
    MT5AccountMismatchError,
    MT5ConnectionError,
    mt5_connection,
)


router = APIRouter(
    prefix="/api/mt5",
    tags=["MetaTrader 5"],
)

position_manager = PositionManager()


class MT5TradingAccountRequest(BaseModel):
    login: int = Field(
        gt=0,
    )

    server: str = Field(
        min_length=1,
        max_length=255,
    )

    account_name: str | None = Field(
        default=None,
        max_length=255,
    )

    currency: str = Field(
        default="USD",
        min_length=1,
        max_length=10,
    )


def get_user_mt5_account(
    db: Session,
    current_user: User,
) -> MT5TradingAccount | None:

    return (
        db.query(MT5TradingAccount)
        .filter(
            MT5TradingAccount.user_id
            == current_user.id
        )
        .first()
    )


def require_verified_mt5_account(
    db: Session,
    current_user: User,
) -> MT5TradingAccount:

    account = get_user_mt5_account(
        db=db,
        current_user=current_user,
    )

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No MT5 trading account is registered "
                "for this user."
            ),
        )

    if not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user's MT5 trading account is inactive.",
        )

    try:
        mt5_connection.verify_account(
            expected_login=account.mt5_login,
            expected_server=account.server,
        )

    except MT5AccountMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )

    except MT5ConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    return account


# ----------------------------------------------------------------------
# REGISTER / UPDATE USER MT5 ACCOUNT
# ----------------------------------------------------------------------


@router.post(
    "/account",
)
def register_mt5_account(
    payload: MT5TradingAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    existing = get_user_mt5_account(
        db=db,
        current_user=current_user,
    )

    duplicate = (
        db.query(MT5TradingAccount)
        .filter(
            MT5TradingAccount.mt5_login
            == payload.login,
            MT5TradingAccount.server
            == payload.server.strip(),
            MT5TradingAccount.user_id
            != current_user.id,
        )
        .first()
    )

    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This MT5 trading account is already "
                "registered to another user."
            ),
        )

    if existing is None:

        account = MT5TradingAccount(
            user_id=current_user.id,
            mt5_login=payload.login,
            server=payload.server.strip(),
            account_name=(
                payload.account_name.strip()
                if payload.account_name
                else None
            ),
            currency=payload.currency.strip().upper(),
            is_active=True,
        )

        db.add(account)

    else:

        existing.mt5_login = payload.login
        existing.server = payload.server.strip()
        existing.account_name = (
            payload.account_name.strip()
            if payload.account_name
            else None
        )
        existing.currency = (
            payload.currency.strip().upper()
        )
        existing.is_active = True

        account = existing

    db.commit()
    db.refresh(account)

    return {
        "status": "registered",
        "account": {
            "id": account.id,
            "login": account.mt5_login,
            "server": account.server,
            "account_name": account.account_name,
            "currency": account.currency,
            "is_active": account.is_active,
        },
    }


# ----------------------------------------------------------------------
# CONNECT
# ----------------------------------------------------------------------


@router.post(
    "/connect",
)
def connect_mt5(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    account = get_user_mt5_account(
        db=db,
        current_user=current_user,
    )

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Register an MT5 trading account "
                "before connecting."
            ),
        )

    if not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The registered MT5 account is inactive.",
        )

    try:
        status_data = mt5_connection.connect()

        mt5_connection.verify_account(
            expected_login=account.mt5_login,
            expected_server=account.server,
        )

        return {
            **status_data,
            "ownership": {
                "verified": True,
                "user_id": current_user.id,
                "mt5_account_id": account.id,
            },
        }

    except MT5AccountMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )

    except MT5ConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )


# ----------------------------------------------------------------------
# STATUS
# ----------------------------------------------------------------------


@router.get(
    "/status",
)
def get_mt5_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    account = require_verified_mt5_account(
        db=db,
        current_user=current_user,
    )

    try:
        status_data = mt5_connection.get_status()

        return {
            **status_data,
            "ownership": {
                "verified": True,
                "user_id": current_user.id,
                "mt5_account_id": account.id,
            },
        }

    except MT5ConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )


# ----------------------------------------------------------------------
# DISCONNECT
# ----------------------------------------------------------------------


@router.post(
    "/disconnect",
)
def disconnect_mt5(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    require_verified_mt5_account(
        db=db,
        current_user=current_user,
    )

    mt5_connection.disconnect()

    return {
        "connected": False,
        "message": "MetaTrader 5 connection closed.",
    }


# ----------------------------------------------------------------------
# POSITIONS
# ----------------------------------------------------------------------


@router.get(
    "/positions",
)
def get_mt5_positions(
    symbol: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    account = require_verified_mt5_account(
        db=db,
        current_user=current_user,
    )

    try:

        positions = position_manager.get_positions(
            symbol=symbol,
        )

        summary = position_manager.summary()

        return {
            "source": "MetaTrader 5",
            "magic": position_manager.magic_number,
            "count": len(positions),
            "positions": positions,
            "summary": summary,
            "ownership": {
                "verified": True,
                "user_id": current_user.id,
                "mt5_account_id": account.id,
            },
        }

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Unable to load MT5 positions: "
                f"{exc}"
            ),
        )


# ----------------------------------------------------------------------
# POSITION SUMMARY
# ----------------------------------------------------------------------


@router.get(
    "/positions/summary",
)
def get_mt5_positions_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    account = require_verified_mt5_account(
        db=db,
        current_user=current_user,
    )

    try:

        return {
            "source": "MetaTrader 5",
            "magic": position_manager.magic_number,
            **position_manager.summary(),
            "ownership": {
                "verified": True,
                "user_id": current_user.id,
                "mt5_account_id": account.id,
            },
        }

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Unable to load MT5 position summary: "
                f"{exc}"
            ),
        )