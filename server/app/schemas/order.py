from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class OrderCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=50)
    side: str
    quantity: Decimal = Field(gt=0)
    entry_price: Decimal = Field(gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("side")
    @classmethod
    def validate_side(cls, value: str) -> str:
        value = value.strip().lower()

        if value not in {"buy", "sell"}:
            raise ValueError("Side must be either buy or sell")

        return value


class OrderCloseRequest(BaseModel):
    close_price: Decimal = Field(
        gt=0,
        description="Price at which the order is closed",
    )


class OrderResponse(BaseModel):
    id: int
    user_id: int
    trading_account_id: int
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    stop_loss: Decimal | None
    take_profit: Decimal | None
    status: str
    profit_loss: Decimal
    opened_at: datetime
    closed_at: datetime | None

    model_config = {
        "from_attributes": True,
    }