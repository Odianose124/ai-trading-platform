from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.mt5.worker_manager import (
    MT5WorkerManagerError,
    mt5_worker_manager,
)



class ExecutionPreviewError(Exception):
    """Raised when an execution preview cannot be created."""


@dataclass
class ExecutionPreview:
    approved: bool
    status: str

    symbol: str
    broker_symbol: Optional[str]

    direction: str
    volume: Optional[Decimal]

    signal_entry_price: Optional[Decimal]
    execution_price: Optional[Decimal]

    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]

    signal_price_deviation: Optional[Decimal]
    signal_price_deviation_percent: Optional[Decimal]

    spread: Optional[Decimal]
    spread_points: Optional[Decimal]

    margin_required: Optional[Decimal]
    free_margin: Optional[Decimal]

    risk_amount: Optional[Decimal]
    risk_percent: Optional[Decimal]

    checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    execution_sent: bool = False

    message: str = ""

    def serialize(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "status": self.status,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "direction": self.direction,
            "volume": self._decimal(self.volume),
            "signal_entry_price": self._decimal(self.signal_entry_price),
            "execution_price": self._decimal(self.execution_price),
            "stop_loss": self._decimal(self.stop_loss),
            "take_profit": self._decimal(self.take_profit),
            "signal_price_deviation": self._decimal(
                self.signal_price_deviation
            ),
            "signal_price_deviation_percent": self._decimal(
                self.signal_price_deviation_percent
            ),
            "market": {
                "spread": self._decimal(self.spread),
                "spread_points": self._decimal(self.spread_points),
            },
            "margin": {
                "required": self._decimal(self.margin_required),
                "free": self._decimal(self.free_margin),
            },
            "risk": {
                "amount": self._decimal(self.risk_amount),
                "percent": self._decimal(self.risk_percent),
            },
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "execution_sent": self.execution_sent,
            "message": self.message,
        }

    @staticmethod
    def _decimal(value: Optional[Decimal]) -> Optional[float]:
        if value is None:
            return None

        return float(value)


class ExecutionPreviewService:
    """
    Creates a final execution preview without sending an MT5 order.

    Flow:

        Trade Setup
            â†“
        Position Size
            â†“
        Broker Validation
            â†“
        Execution Preview
            â†“
        Final Confirmation
            â†“
        MT5 order_send()
    """

    # Maximum allowed difference between the signal entry and
    # the current executable market price before confirmation
    # is considered stale.
    MAX_SIGNAL_PRICE_DEVIATION_PERCENT = Decimal("0.25")

    @staticmethod
    def _to_decimal(value: Any, field_name: str) -> Decimal:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ExecutionPreviewError(
                f"Invalid {field_name}: {value}"
            ) from exc

        if not result.is_finite():
            raise ExecutionPreviewError(
                f"Invalid {field_name}: {value}"
            )

        return result

    @staticmethod
    def _normalize_direction(direction: str) -> str:
        normalized = str(direction).strip().lower()

        mapping = {
            "buy": "buy",
            "long": "buy",
            "sell": "sell",
            "short": "sell",
        }

        if normalized not in mapping:
            raise ExecutionPreviewError(
                "Direction must be buy, sell, long, or short."
            )

        return mapping[normalized]

    def _calculate_signal_deviation(
        self,
        signal_entry_price: Decimal,
        execution_price: Decimal,
    ) -> tuple[Decimal, Decimal]:
        deviation = abs(execution_price - signal_entry_price)

        if signal_entry_price == 0:
            return deviation, Decimal("0")

        deviation_percent = (
            deviation / abs(signal_entry_price)
        ) * Decimal("100")

        return deviation, deviation_percent

    def _calculate_risk(
        self,
        mt5_account_id: int,
        user_id: int,
        direction: str,
        execution_price: Decimal,
        stop_loss: Decimal,
        volume: Decimal,
        broker_symbol: str,
    ) -> Optional[Decimal]:
        """
        Calculates an approximate monetary risk using MT5 tick data.

        This is only an execution-preview risk estimate.
        Final broker execution remains responsible for actual fills.
        """

        try:
            symbol_info = mt5_worker_manager.symbol_info(
                mt5_account_id=mt5_account_id,
                user_id=user_id,
                symbol=broker_symbol,
            )
        except MT5WorkerManagerError:
            return None

        if symbol_info is None:
            return None

        tick_size = Decimal(str(symbol_info.get("trade_tick_size", 0) or 0))
        tick_value = Decimal(
        str(symbol_info.get("trade_tick_value", 0) or 0)
    )

        if tick_size <= 0 or tick_value <= 0:
            return None

        stop_distance = abs(execution_price - stop_loss)

        if stop_distance <= 0:
            return None

        ticks = stop_distance / tick_size

        return ticks * tick_value * volume

    def preview(
        self,
        *,
        mt5_account_id: int,
        user_id: int,
        symbol: str,
        direction: str,
        volume: Any,
        signal_entry_price: Any,
        stop_loss: Any,
        take_profit: Any,
        risk_percent: Any = None,
    ) -> ExecutionPreview:

        application_symbol = str(symbol).strip().upper()

        if not application_symbol:
            raise ExecutionPreviewError("Symbol is required.")

        normalized_direction = self._normalize_direction(direction)

        requested_volume = self._to_decimal(volume, "volume")
        signal_entry = self._to_decimal(
            signal_entry_price,
            "signal_entry_price",
        )
        requested_stop_loss = self._to_decimal(
            stop_loss,
            "stop_loss",
        )
        requested_take_profit = self._to_decimal(
            take_profit,
            "take_profit",
        )

        if requested_volume <= 0:
            raise ExecutionPreviewError(
                "Volume must be greater than zero."
            )

        if signal_entry <= 0:
            raise ExecutionPreviewError(
                "Signal entry price must be greater than zero."
            )

        if requested_stop_loss <= 0:
            raise ExecutionPreviewError(
                "Stop loss must be greater than zero."
            )

        if requested_take_profit <= 0:
            raise ExecutionPreviewError(
                "Take profit must be greater than zero."
            )

        checks: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []

        try:
            validation_data = mt5_worker_manager.validate_trade(
                mt5_account_id=mt5_account_id,
                user_id=user_id,
                symbol=application_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                entry_price=signal_entry,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
            )

            class WorkerValidationResult:
                pass

            validation = WorkerValidationResult()

            for key, value in validation_data.items():
                setattr(
                    validation,
                    key,
                    value,
                )

        except MT5WorkerManagerError as exc:
            return ExecutionPreview(
                approved=False,
                status="validation_error",
                symbol=application_symbol,
                broker_symbol=None,
                direction=normalized_direction,
                volume=requested_volume,
                signal_entry_price=signal_entry,
                execution_price=None,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=None,
                signal_price_deviation_percent=None,
                spread=None,
                spread_points=None,
                margin_required=None,
                free_margin=None,
                risk_amount=None,
                risk_percent=None,
                checks=[],
                warnings=[],
                errors=[str(exc)],
                execution_sent=False,
                message="Execution preview could not be created.",
            )

        broker_symbol = validation.broker_symbol
        execution_price_raw = validation.execution_price

        if execution_price_raw is None:
            errors.append(
                "Broker did not provide a current executable price."
            )

            return ExecutionPreview(
                approved=False,
                status="no_execution_price",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                signal_entry_price=signal_entry,
                execution_price=None,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=None,
                signal_price_deviation_percent=None,
                spread=None,
                spread_points=None,
                margin_required=None,
                free_margin=None,
                risk_amount=None,
                risk_percent=None,
                checks=validation.checks,
                warnings=validation.warnings,
                errors=errors,
                execution_sent=False,
                message="No executable market price is available.",
            )

        execution_price = self._to_decimal(
            execution_price_raw,
            "execution_price",
        )

        deviation, deviation_percent = self._calculate_signal_deviation(
            signal_entry,
            execution_price,
        )

        checks.extend(validation.checks)

        warnings.extend(validation.warnings)

        if deviation_percent > self.MAX_SIGNAL_PRICE_DEVIATION_PERCENT:
            warnings.append(
                "Signal entry price is materially different from "
                "the current executable market price."
            )

            warnings.append(
                "Execution confirmation should be rejected until "
                "the trading signal is refreshed."
            )

        else:
            checks.append(
                "Signal entry price remains within the allowed "
                "execution deviation threshold"
            )

        # Never execute using the stale signal entry.
        # The preview always exposes the live executable price.
        checks.append(
            "Execution preview uses the broker's current executable price"
        )

        checks.append(
            "No MT5 order has been sent"
        )

        risk_amount = self._calculate_risk(
            mt5_account_id=mt5_account_id,
            user_id=user_id,
            direction=normalized_direction,
            execution_price=execution_price,
            stop_loss=requested_stop_loss,
            volume=requested_volume,
            broker_symbol=broker_symbol,
        )

        normalized_risk_percent: Optional[Decimal] = None

        if risk_percent is not None:
            try:
                normalized_risk_percent = self._to_decimal(
                    risk_percent,
                    "risk_percent",
                )
            except ExecutionPreviewError:
                warnings.append(
                    "Risk percentage supplied by the signal could "
                    "not be normalized."
                )

        if risk_amount is None:
            warnings.append(
                "Monetary risk could not be calculated from the "
                "broker tick specification."
            )

        # If broker validation itself failed, execution preview
        # must remain blocked.
        if not validation.approved:
            errors.extend(validation.errors)

        # A stale signal is not executable.
        if deviation_percent > self.MAX_SIGNAL_PRICE_DEVIATION_PERCENT:
            errors.append(
                "Execution blocked because the signal entry price "
                "is stale relative to the current executable price."
            )

        approved = len(errors) == 0

        status = "ready_for_confirmation" if approved else "blocked"

        if approved:
            message = (
                "Execution preview passed. "
                "No MT5 order has been sent. "
                "Final user confirmation is required before execution."
            )
        else:
            message = (
                "Execution preview blocked. "
                "Refresh the signal and revalidate the trade before execution."
            )

        return ExecutionPreview(
            approved=approved,
            status=status,
            symbol=application_symbol,
            broker_symbol=broker_symbol,
            direction=normalized_direction,
            volume=requested_volume,
            signal_entry_price=signal_entry,
            execution_price=execution_price,
            stop_loss=requested_stop_loss,
            take_profit=requested_take_profit,
            signal_price_deviation=deviation,
            signal_price_deviation_percent=deviation_percent,
            spread=(
                self._to_decimal(
                    validation_data["market"]["spread"],
                    "spread",
                )
                if validation_data["market"]["spread"] is not None
                else None
            ),
            spread_points=(
                self._to_decimal(
                    validation_data["market"]["spread_points"],
                    "spread_points",
                )
                if validation_data["market"]["spread_points"] is not None
                else None
            ),
            margin_required=(
                self._to_decimal(
                    validation_data["margin_required"],
                    "margin_required",
                )
                if validation_data["margin_required"] is not None
                else None
            ),
            free_margin=(
                self._to_decimal(
                    validation_data["free_margin"],
                    "free_margin",
                )
                if validation_data["free_margin"] is not None
                else None
            ),
            risk_amount=risk_amount,
            risk_percent=normalized_risk_percent,
            checks=checks,
            warnings=warnings,
            errors=errors,
            execution_sent=False,
            message=message,
        )


execution_preview_service = ExecutionPreviewService()
