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
from app.models.mt5_trading_account import MT5TradingAccount
from app.models.user import User
from app.mt5.worker_manager import (
    MT5WorkerManagerError,
    mt5_worker_manager,
)


router = APIRouter(
    prefix="/api/mt5",
    tags=["MetaTrader 5"],
)


class PendingOrderModifyRequest(BaseModel):
    price: float | None = Field(
        default=None,
        gt=0,
    )

    stop_loss: float | None = Field(
        default=None,
        ge=0,
    )

    take_profit: float | None = Field(
        default=None,
        ge=0,
    )


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


def require_registered_mt5_account(
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

        if (
            existing.mt5_login != payload.login
            or existing.server != payload.server.strip()
        ):
            try:
                mt5_worker_manager.stop_account(
                    mt5_account_id=existing.id,
                    user_id=current_user.id,
                )
            except MT5WorkerManagerError:
                pass

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

    account = require_registered_mt5_account(
        db=db,
        current_user=current_user,
    )

    try:
        worker_status = mt5_worker_manager.start_account(
            account=account,
        )

        return {
            **worker_status,
            "ownership": {
                "verified": True,
                "user_id": current_user.id,
                "mt5_account_id": account.id,
            },
        }

    except MT5WorkerManagerError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


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

    account = require_registered_mt5_account(
        db=db,
        current_user=current_user,
    )

    try:
        status_data = mt5_worker_manager.status_for_account(
            mt5_account_id=account.id,
            user_id=current_user.id,
        )

        return {
            **status_data,
            "ownership": {
                "verified": True,
                "user_id": current_user.id,
                "mt5_account_id": account.id,
            },
        }

    except MT5WorkerManagerError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


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

    account = require_registered_mt5_account(
        db=db,
        current_user=current_user,
    )

    try:
        mt5_worker_manager.stop_account(
            mt5_account_id=account.id,
            user_id=current_user.id,
        )

        return {
            "connected": False,
            "message": "MetaTrader 5 account worker stopped.",
            "ownership": {
                "verified": True,
                "user_id": current_user.id,
                "mt5_account_id": account.id,
            },
        }

    except MT5WorkerManagerError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


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

    account = require_registered_mt5_account(
        db=db,
        current_user=current_user,
    )

    try:
        positions = mt5_worker_manager.get_positions(
            mt5_account_id=account.id,
            user_id=current_user.id,
            symbol=symbol,
        )

        return {
            "mt5_account_id": account.id,
            "user_id": current_user.id,
            "positions": positions,
            "count": len(positions),
        }

    except MT5WorkerManagerError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


# ----------------------------------------------------------------------
# PENDING ORDERS
# ----------------------------------------------------------------------


@router.get(
    "/pending-orders",
)
def get_mt5_pending_orders(
    symbol: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    account = require_registered_mt5_account(
        db=db,
        current_user=current_user,
    )

    try:
        pending_orders = mt5_worker_manager.get_pending_orders(
            mt5_account_id=account.id,
            user_id=current_user.id,
            symbol=symbol,
        )

        return {
            "mt5_account_id": account.id,
            "user_id": current_user.id,
            "pending_orders": pending_orders,
            "count": len(pending_orders),
        }

    except MT5WorkerManagerError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

# ----------------------------------------------------------------------
# CANCEL PENDING ORDER
# ----------------------------------------------------------------------


@router.delete(
    "/pending-orders/{ticket}",
)
def cancel_mt5_pending_order(
    ticket: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = require_registered_mt5_account(
        db=db,
        current_user=current_user,
    )

    try:
        result = mt5_worker_manager.cancel_pending_order(
            mt5_account_id=account.id,
            user_id=current_user.id,
            ticket=ticket,
        )

        return {
            "mt5_account_id": account.id,
            "user_id": current_user.id,
            "ticket": ticket,
            "result": result,
        }

    except MT5WorkerManagerError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


# ----------------------------------------------------------------------
# MODIFY PENDING ORDER
# ----------------------------------------------------------------------


@router.patch(
    "/pending-orders/{ticket}",
)
def modify_mt5_pending_order(
    ticket: int,
    payload: PendingOrderModifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if (
        payload.price is None
        and payload.stop_loss is None
        and payload.take_profit is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "At least one pending-order field must be "
                "provided for modification."
            ),
        )

    account = require_registered_mt5_account(
        db=db,
        current_user=current_user,
    )

    try:
        result = mt5_worker_manager.modify_pending_order(
            mt5_account_id=account.id,
            user_id=current_user.id,
            ticket=ticket,
            price=payload.price,
            stop_loss=payload.stop_loss,
            take_profit=payload.take_profit,
        )

        return {
            "mt5_account_id": account.id,
            "user_id": current_user.id,
            "ticket": ticket,
            "result": result,
        }

    except MT5WorkerManagerError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


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

    account = require_registered_mt5_account(
        db=db,
        current_user=current_user,
    )

    try:
        positions = mt5_worker_manager.get_positions(
            mt5_account_id=account.id,
            user_id=current_user.id,
        )

        total_volume = sum(
            float(position.get("volume", 0))
            for position in positions
        )

        total_profit = sum(
            float(position.get("profit", 0))
            for position in positions
        )

        total_swap = sum(
            float(position.get("swap", 0))
            for position in positions
        )

        buy_positions = sum(
            1
            for position in positions
            if position.get("type") == "buy"
        )

        sell_positions = sum(
            1
            for position in positions
            if position.get("type") == "sell"
        )

        return {
            "mt5_account_id": account.id,
            "user_id": current_user.id,
            "total_positions": len(positions),
            "buy_positions": buy_positions,
            "sell_positions": sell_positions,
            "total_volume": total_volume,
            "total_profit": total_profit,
            "total_swap": total_swap,
        }

    except MT5WorkerManagerError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
