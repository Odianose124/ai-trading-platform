from decimal import Decimal

from pydantic import BaseModel, Field


class DepositRequest(BaseModel):
    amount: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=2,
    )