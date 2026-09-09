from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TransactionRequest(BaseModel):
    amount: Decimal = Field(
        gt=0,
        description="Amount of funds",
    )


class DepositRequest(TransactionRequest):
    pass


class WithdrawalRequest(TransactionRequest):
    pass


class TransactionResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int = Field(
        description="Unique transaction ID",
    )

    user_id: int = Field(
        description="ID of the user who owns the transaction",
    )

    trading_account_id: int = Field(
        description="ID of the trading account",
    )

    transaction_type: str = Field(
        description="Type of transaction",
    )

    amount: Decimal = Field(
        description="Transaction amount",
    )

    currency: str = Field(
        description="Transaction currency",
    )

    status: str = Field(
        description="Transaction status",
    )

    reference: str = Field(
        description="Unique transaction reference",
    )

    description: str | None = Field(
        default=None,
        description="Optional transaction description",
    )

    created_at: datetime = Field(
        description="Transaction creation timestamp",
    )