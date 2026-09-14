from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import isfinite

from sqlalchemy.orm import Session

from app.models.trade_intent import TradeIntent
from app.models.user_settings import UserSettings


class TradeIntentError(Exception):
    """Raised when a trade intent operation cannot be completed."""


@dataclass
class TradeIntentResult:
    approved: bool
    status: str
    intent_id: int | None
    user_id: int | None
    symbol: str | None
    broker_symbol: str | None
    direction: str | None
    volume: Decimal | None
    signal_entry_price: Decimal | None
    execution_price: Decimal | None
    stop_loss: Decimal | None
    take_profit: Decimal | None
    risk_percent: Decimal | None
    expires_at: datetime | None
    checks: list[str]
    warnings: list[str]
    errors: list[str]
    message: str

    def serialize(self) -> dict:
        return {
            "approved": self.approved,
            "status": self.status,
            "intent_id": self.intent_id,
            "user_id": self.user_id,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "direction": self.direction,
            "volume": (
                float(self.volume)
                if self.volume is not None
                else None
            ),
            "signal_entry_price": (
                float(self.signal_entry_price)
                if self.signal_entry_price is not None
                else None
            ),
            "execution_price": (
                float(self.execution_price)
                if self.execution_price is not None
                else None
            ),
            "stop_loss": (
                float(self.stop_loss)
                if self.stop_loss is not None
                else None
            ),
            "take_profit": (
                float(self.take_profit)
                if self.take_profit is not None
                else None
            ),
            "risk_percent": (
                float(self.risk_percent)
                if self.risk_percent is not None
                else None
            ),
            "expires_at": (
                self.expires_at.isoformat()
                if self.expires_at is not None
                else None
            ),
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "message": self.message,
        }


class TradeIntentService:
    INTENT_VALIDITY_SECONDS = 60
    DEFAULT_MAX_RISK_PERCENT = Decimal("2")

    def _to_decimal(self, value, field_name: str) -> Decimal:
        try:
            decimal_value = Decimal(str(value))
        except Exception as exc:
            raise TradeIntentError(
                f"{field_name} must be a valid number."
            ) from exc

        if not decimal_value.is_finite():
            raise TradeIntentError(
                f"{field_name} must be finite."
            )

        return decimal_value

    def _normalize_direction(self, direction: str) -> str:
        normalized = str(direction).strip().lower()

        if normalized in {"long", "buy"}:
            return "buy"

        if normalized in {"short", "sell"}:
            return "sell"

        raise TradeIntentError(
            "Direction must be long, short, buy, or sell."
        )

    def _result_from_intent(
        self,
        intent: TradeIntent,
        *,
        approved: bool,
        status: str,
        checks: list[str] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        message: str = "",
    ) -> TradeIntentResult:
        return TradeIntentResult(
            approved=approved,
            status=status,
            intent_id=intent.id,
            user_id=intent.user_id,
            symbol=intent.symbol,
            broker_symbol=intent.broker_symbol,
            direction=intent.direction,
            volume=intent.volume,
            signal_entry_price=intent.signal_entry_price,
            execution_price=intent.execution_price,
            stop_loss=intent.stop_loss,
            take_profit=intent.take_profit,
            risk_percent=intent.risk_percent,
            expires_at=intent.expires_at,
            checks=checks or [],
            warnings=warnings or [],
            errors=errors or [],
            message=message,
        )

    def create(
        self,
        db: Session,
        user_id: int,
        symbol: str,
        broker_symbol: str,
        direction: str,
        volume,
        signal_entry_price,
        execution_price,
        stop_loss,
        take_profit,
        risk_percent=None,
        signal_price_deviation_percent=None,
        margin_required=None,
        free_margin=None,
        preview_status: str = "ready_for_confirmation",
        warnings: list[str] | None = None,
    ) -> TradeIntentResult:
        if user_id is None:
            raise TradeIntentError(
                "Authenticated user is required."
            )

        normalized_symbol = str(symbol).strip().upper()
        normalized_broker_symbol = str(broker_symbol).strip()

        if not normalized_symbol:
            raise TradeIntentError("Symbol is required.")

        if not normalized_broker_symbol:
            raise TradeIntentError(
                "Broker symbol is required."
            )

        normalized_direction = self._normalize_direction(direction)

        volume_decimal = self._to_decimal(
            volume,
            "Volume",
        )

        signal_entry_decimal = self._to_decimal(
            signal_entry_price,
            "Signal entry price",
        )

        execution_decimal = self._to_decimal(
            execution_price,
            "Execution price",
        )

        stop_loss_decimal = self._to_decimal(
            stop_loss,
            "Stop loss",
        )

        take_profit_decimal = self._to_decimal(
            take_profit,
            "Take profit",
        )

        if volume_decimal <= 0:
            raise TradeIntentError(
                "Volume must be greater than zero."
            )

        for value, field_name in (
            (signal_entry_decimal, "Signal entry price"),
            (execution_decimal, "Execution price"),
            (stop_loss_decimal, "Stop loss"),
            (take_profit_decimal, "Take profit"),
        ):
            if value <= 0:
                raise TradeIntentError(
                    f"{field_name} must be greater than zero."
                )

        if normalized_direction == "buy":
            if stop_loss_decimal >= execution_decimal:
                raise TradeIntentError(
                    "For a buy trade, stop loss must be below "
                    "the execution price."
                )

            if take_profit_decimal <= execution_decimal:
                raise TradeIntentError(
                    "For a buy trade, take profit must be above "
                    "the execution price."
                )

        else:
            if stop_loss_decimal <= execution_decimal:
                raise TradeIntentError(
                    "For a sell trade, stop loss must be above "
                    "the execution price."
                )

            if take_profit_decimal >= execution_decimal:
                raise TradeIntentError(
                    "For a sell trade, take profit must be below "
                    "the execution price."
                )

        risk_decimal = None

        if risk_percent is not None:
            risk_decimal = self._to_decimal(
                risk_percent,
                "Risk percent",
            )

            if risk_decimal <= 0:
                raise TradeIntentError(
                    "Risk percent must be greater than zero."
                )

            # -----------------------------------------------------
            # USER-SPECIFIC MAXIMUM RISK
            # -----------------------------------------------------
            #
            # The trading engine must never rely on a frontend
            # limit. The user's persisted trading preference is
            # loaded directly from the database here.
            #
            # If settings do not exist for any reason, fall back
            # to the original safe 2% ceiling.
            # -----------------------------------------------------

            user_settings = (
                db.query(UserSettings)
                .filter(
                    UserSettings.user_id == user_id
                )
                .first()
            )

            configured_max_risk = (
                Decimal(
                    str(
                        user_settings.max_risk_percent
                    )
                )
                if user_settings is not None
                else self.DEFAULT_MAX_RISK_PERCENT
            )

            if risk_decimal > configured_max_risk:
                raise TradeIntentError(
                    "Risk percent cannot exceed your "
                    f"configured maximum risk of "
                    f"{configured_max_risk}%."
                )

        deviation_decimal = None

        if signal_price_deviation_percent is not None:
            deviation_decimal = self._to_decimal(
                signal_price_deviation_percent,
                "Signal price deviation percent",
            )

            if deviation_decimal < 0:
                raise TradeIntentError(
                    "Signal price deviation percent "
                    "cannot be negative."
                )

        margin_decimal = None

        if margin_required is not None:
            margin_decimal = self._to_decimal(
                margin_required,
                "Margin required",
            )

            if margin_decimal < 0:
                raise TradeIntentError(
                    "Margin required cannot be negative."
                )

        free_margin_decimal = None

        if free_margin is not None:
            free_margin_decimal = self._to_decimal(
                free_margin,
                "Free margin",
            )

            if free_margin_decimal < 0:
                raise TradeIntentError(
                    "Free margin cannot be negative."
                )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(
            seconds=self.INTENT_VALIDITY_SECONDS
        )

        intent = TradeIntent(
            user_id=user_id,
            symbol=normalized_symbol,
            broker_symbol=normalized_broker_symbol,
            direction=normalized_direction,
            volume=volume_decimal,
            signal_entry_price=signal_entry_decimal,
            execution_price=execution_decimal,
            stop_loss=stop_loss_decimal,
            take_profit=take_profit_decimal,
            risk_percent=risk_decimal,
            preview_status=preview_status,
            confirmation_status="pending",
            execution_status="not_executed",
            signal_price_deviation_percent=deviation_decimal,
            margin_required=margin_decimal,
            free_margin=free_margin_decimal,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )

        db.add(intent)
        db.commit()
        db.refresh(intent)

        checks = [
            "Authenticated user ownership recorded",
            "Trading symbol validated",
            "Broker symbol associated with trade intent",
            "Trade direction validated",
            "Volume validated",
            "Execution price validated",
            "Stop loss geometry validated",
            "Take profit geometry validated",
            "Trade intent stored server-side",
            "Trade intent expiration recorded",
        ]

        if margin_decimal is not None:
            checks.append(
                "Broker margin requirement recorded"
            )

        if free_margin_decimal is not None:
            checks.append(
                "Broker free margin recorded"
            )

        return self._result_from_intent(
            intent,
            approved=True,
            status="created",
            checks=checks,
            warnings=warnings or [],
            errors=[],
            message=(
                "Trade intent created successfully. "
                "No MT5 order has been sent. "
                "Final confirmation is still required."
            ),
        )

    def get_intent(
        self,
        db: Session,
        intent_id: int,
        user_id: int,
    ) -> TradeIntentResult:
        intent = (
            db.query(TradeIntent)
            .filter(
                TradeIntent.id == intent_id,
                TradeIntent.user_id == user_id,
            )
            .first()
        )

        if intent is None:
            raise TradeIntentError(
                "Trade intent not found."
            )

        return self._result_from_intent(
            intent,
            approved=True,
            status="retrieved",
            checks=[
                "Authenticated user ownership verified",
                "Trade intent retrieved without changing state",
            ],
            warnings=[],
            errors=[],
            message=(
                "Trade intent retrieved successfully. "
                "No confirmation or execution state was changed."
            ),
        )

    def validate_for_confirmation(
        self,
        db: Session,
        intent_id: int,
        user_id: int,
    ) -> TradeIntentResult:
        intent = (
            db.query(TradeIntent)
            .filter(
                TradeIntent.id == intent_id,
                TradeIntent.user_id == user_id,
            )
            .first()
        )

        if intent is None:
            raise TradeIntentError(
                "Trade intent not found."
            )

        now = datetime.now(timezone.utc)

        if intent.confirmation_status != "pending":
            return self._result_from_intent(
                intent,
                approved=False,
                status="already_processed",
                errors=[
                    "Trade intent has already been processed."
                ],
                message=(
                    "Trade intent is no longer awaiting "
                    "confirmation."
                ),
            )

        if intent.execution_status != "not_executed":
            return self._result_from_intent(
                intent,
                approved=False,
                status="already_processed",
                errors=[
                    "Trade intent execution has already "
                    "been processed."
                ],
                message=(
                    "Trade intent is no longer eligible "
                    "for confirmation."
                ),
            )

        if intent.expires_at is None:
            intent.confirmation_status = "expired"
            intent.execution_status = "blocked"
            intent.error_message = (
                "Trade intent has no expiration time."
            )
            intent.updated_at = now

            db.commit()
            db.refresh(intent)

            return self._result_from_intent(
                intent,
                approved=False,
                status="expired",
                errors=[
                    "Trade intent has no expiration time."
                ],
                message="Trade intent expired.",
            )

        expires_at = intent.expires_at

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(
                tzinfo=timezone.utc
            )

        if now >= expires_at:
            intent.confirmation_status = "expired"
            intent.execution_status = "blocked"
            intent.error_message = (
                "Trade intent expired before confirmation."
            )
            intent.updated_at = now

            db.commit()
            db.refresh(intent)

            return self._result_from_intent(
                intent,
                approved=False,
                status="expired",
                errors=[
                    "Trade intent expired before confirmation."
                ],
                message=(
                    "Trade intent has expired and cannot "
                    "be confirmed."
                ),
            )

        return self._result_from_intent(
            intent,
            approved=True,
            status="awaiting_confirmation",
            checks=[
                "Authenticated user ownership verified",
                "Trade intent is pending",
                "Trade intent has not been executed",
                "Trade intent expiration verified",
            ],
            warnings=[],
            errors=[],
            message=(
                "Trade intent is valid and awaiting "
                "final confirmation."
            ),
        )


trade_intent_service = TradeIntentService()