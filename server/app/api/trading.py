from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database.connection import get_db
from app.models.user import User
from app.schemas.order import (
    OrderCloseRequest,
    OrderCreate,
    OrderResponse,
)
from app.schemas.transaction import (
    DepositRequest,
    WithdrawalRequest,
)
from app.services.order_service import (
    close_order,
    create_order,
    get_user_order,
    get_user_orders,
)
from app.services.trading_account_service import (
    deposit_funds,
    get_trading_account,
    withdraw_funds,
)


router = APIRouter(
    prefix="/api/trading",
    tags=["Trading"],
)


@router.get("/account")
def get_my_trading_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = get_trading_account(db, current_user.id)

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trading account not found",
        )

    return {
        "id": account.id,
        "user_id": account.user_id,
        "balance": account.balance,
        "available_balance": account.available_balance,
        "currency": account.currency,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }


@router.post("/deposit")
def deposit(
    deposit_data: DepositRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        account = deposit_funds(
            db=db,
            user_id=current_user.id,
            amount=deposit_data.amount,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return {
        "message": "Deposit completed successfully",
        "account": {
            "id": account.id,
            "user_id": account.user_id,
            "balance": account.balance,
            "available_balance": account.available_balance,
            "currency": account.currency,
            "updated_at": account.updated_at,
        },
    }


@router.post("/withdraw")
def withdraw(
    withdrawal_data: WithdrawalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        account = withdraw_funds(
            db=db,
            user_id=current_user.id,
            amount=withdrawal_data.amount,
        )

    except ValueError as exc:
        detail = str(exc)

        if detail == "Insufficient available balance":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail,
            )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )

    return {
        "message": "Withdrawal completed successfully",
        "account": {
            "id": account.id,
            "user_id": account.user_id,
            "balance": account.balance,
            "available_balance": account.available_balance,
            "currency": account.currency,
            "updated_at": account.updated_at,
        },
    }


@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def open_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return create_order(
            db=db,
            user_id=current_user.id,
            order_data=order_data,
        )

    except ValueError as exc:
        detail = str(exc)

        if detail == "Insufficient available balance":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail,
            )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )


@router.post(
    "/orders/{order_id}/close",
    response_model=OrderResponse,
)
def close_existing_order(
    order_id: int,
    close_data: OrderCloseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return close_order(
            db=db,
            user_id=current_user.id,
            order_id=order_id,
            close_price=close_data.close_price,
        )

    except ValueError as exc:
        detail = str(exc)

        if detail == "Order not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=detail,
            )

        if detail == "Trading account not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=detail,
            )

        if detail == "Order is already closed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail,
            )

        if detail == "Invalid order side":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail,
            )

        if detail == "Calculated closing amount cannot be negative":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail,
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )


@router.get(
    "/orders",
    response_model=list[OrderResponse],
)
def list_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_user_orders(
        db=db,
        user_id=current_user.id,
    )


@router.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = get_user_order(
        db=db,
        user_id=current_user.id,
        order_id=order_id,
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return order