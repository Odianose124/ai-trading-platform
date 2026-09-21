from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


from app.mt5.worker_manager import (
    mt5_worker_manager,
    MT5WorkerManagerError,
)


class MT5ExecutionError(Exception):
    """Raised when an MT5 trade cannot be executed."""


@dataclass
class MT5ExecutionResult:
    approved: bool
    status: str

    symbol: str
    broker_symbol: Optional[str]

    direction: str
    volume: Optional[Decimal]

    requested_entry_price: Optional[Decimal]
    execution_price: Optional[Decimal]

    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]

    signal_price_deviation: Optional[Decimal]
    signal_price_deviation_percent: Optional[Decimal]

    order_ticket: Optional[int] = None
    deal_ticket: Optional[int] = None

    retcode: Optional[int] = None
    retcode_description: Optional[str] = None

    margin_required: Optional[Decimal] = None
    free_margin: Optional[Decimal] = None

    risk_amount: Optional[Decimal] = None
    risk_percent: Optional[Decimal] = None

    checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    execution_sent: bool = False

    execution_mode: str = "market"
    order_type: str = "MARKET"
    pending_order_status: str = "not_applicable"
    pending_order_placed_at: Optional[str] = None
    filled_position_ticket: Optional[int] = None

    message: str = ""

    def serialize(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "status": self.status,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "direction": self.direction,
            "volume": self._number(self.volume),
            "requested_entry_price": self._number(
                self.requested_entry_price
            ),
            "execution_price": self._number(
                self.execution_price
            ),
            "execution_mode": self.execution_mode,
            "order_type": self.order_type,
            "pending_order_status": self.pending_order_status,
            "pending_order_placed_at": self.pending_order_placed_at,
            "filled_position_ticket": self.filled_position_ticket,
            "stop_loss": self._number(self.stop_loss),
            "take_profit": self._number(self.take_profit),
            "signal_price_deviation": self._number(
                self.signal_price_deviation
            ),
            "signal_price_deviation_percent": self._number(
                self.signal_price_deviation_percent
            ),
            "order_ticket": self.order_ticket,
            "deal_ticket": self.deal_ticket,
            "retcode": self.retcode,
            "retcode_description": self.retcode_description,
            "margin": {
                "required": self._number(self.margin_required),
                "free": self._number(self.free_margin),
            },
            "risk": {
                "amount": self._number(self.risk_amount),
                "percent": self._number(self.risk_percent),
            },
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "execution_sent": self.execution_sent,
            "message": self.message,
        }

    @staticmethod
    def _number(value: Optional[Decimal]) -> Optional[float]:
        if value is None:
            return None

        return float(value)


class MT5ExecutionService:
    """
    Final MT5 execution layer.

    IMPORTANT:
    Actual broker execution is delegated to the isolated
    account worker. This service prepares and validates
    the platform-level execution request.

    The service performs fresh broker validation immediately
    before sending the order.
    """

    MAX_SIGNAL_PRICE_DEVIATION_PERCENT = Decimal("0.25")

    # Safety requirement:
    # MT5 execution requires an explicitly enabled execution request.
    REQUIRE_EXPLICIT_EXECUTION = True

    @staticmethod
    def _decimal(
        value: Any,
        field_name: str,
    ) -> Decimal:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise MT5ExecutionError(
                f"Invalid {field_name}: {value}"
            ) from exc

        if not result.is_finite():
            raise MT5ExecutionError(
                f"Invalid {field_name}: {value}"
            )

        return result

    @staticmethod
    def _direction(direction: str) -> str:
        value = str(direction).strip().lower()

        if value in {"buy", "long"}:
            return "buy"

        if value in {"sell", "short"}:
            return "sell"

        raise MT5ExecutionError(
            "Direction must be buy, sell, long, or short."
        )

    @staticmethod
    def _calculate_deviation(
        signal_entry: Decimal,
        execution_price: Decimal,
    ) -> tuple[Decimal, Decimal]:

        difference = abs(
            execution_price - signal_entry
        )

        if signal_entry == 0:
            return difference, Decimal("0")

        percentage = (
            difference
            / abs(signal_entry)
            * Decimal("100")
        )

        return difference, percentage

    @staticmethod
    def _risk_amount(
        *,
        mt5_account_id: int,
        user_id: int,
        broker_symbol: str,
        direction: str,
        execution_price: Decimal,
        stop_loss: Decimal,
        volume: Decimal,
    ) -> Optional[Decimal]:

        symbol_info = mt5_worker_manager.symbol_info(
            mt5_account_id=mt5_account_id,
            user_id=user_id,
            symbol=broker_symbol,
        )

        if symbol_info is None:
            return None

        tick_size = Decimal(
            str(
                symbol_info.get(
                    "trade_tick_size",
                    0,
                )
                or 0
            )
        )

        tick_value = Decimal(
            str(
                symbol_info.get(
                    "trade_tick_value",
                    0,
                )
                or 0
            )
        )

        if tick_size <= 0 or tick_value <= 0:
            return None

        distance = abs(
            execution_price - stop_loss
        )

        if distance <= 0:
            return None

        ticks = distance / tick_size

        return ticks * tick_value * volume

    def _select_filling_mode(
        self,
        symbol_info: Any,
    ) -> str:
        filling_flags = int(
            symbol_info.get(
                "filling_mode",
                0,
            )
            or 0
        )

        # MT5 symbol filling flags:
        # FOK = 1
        # IOC = 2
        #
        # Keep these as platform-level semantic values here.
        # The isolated MT5 worker converts them to MT5-native constants.
        symbol_fok = 1
        symbol_ioc = 2

        if filling_flags & symbol_ioc:
            return "IOC"

        if filling_flags & symbol_fok:
            return "FOK"

        raise MT5ExecutionError(
            "Broker does not advertise a supported FOK or IOC "
            "filling policy for market execution."
        )

    def _classify_order_type(
        self,
        *,
        direction: str,
        requested_entry: Decimal,
        ask: Decimal,
        bid: Decimal,
        tolerance: Decimal,
    ) -> tuple[str, str]:
        """
        Classify the requested entry against the current executable price.

        BUY:
          requested ~= Ask -> MARKET
          requested > Ask  -> BUY_STOP
          requested < Ask  -> BUY_LIMIT

        SELL:
          requested ~= Bid -> MARKET
          requested < Bid  -> SELL_STOP
          requested > Bid  -> SELL_LIMIT
        """

        if direction == "buy":
            market_price = ask

            if abs(requested_entry - market_price) <= tolerance:
                return "market", "MARKET"

            if requested_entry > market_price:
                return "pending", "BUY_STOP"

            return "pending", "BUY_LIMIT"

        market_price = bid

        if abs(requested_entry - market_price) <= tolerance:
            return "market", "MARKET"

        if requested_entry < market_price:
            return "pending", "SELL_STOP"

        return "pending", "SELL_LIMIT"

    def _mt5_order_type(
        self,
        *,
        direction: str,
        execution_mode: str,
        order_type_name: str,
    ) -> str:
        if execution_mode == "market":
            return (
                "BUY"
                if direction == "buy"
                else "SELL"
            )

        allowed_types = {
            "BUY_LIMIT",
            "BUY_STOP",
            "SELL_LIMIT",
            "SELL_STOP",
        }

        if order_type_name not in allowed_types:
            raise MT5ExecutionError(
                f"Unsupported pending order type: {order_type_name}"
            )

        return order_type_name

    def execute(
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
        confirmation: bool = False,
        comment: str = "AI Trading Platform",
    ) -> MT5ExecutionResult:

        application_symbol = str(symbol).strip().upper()

        if not application_symbol:
            raise MT5ExecutionError(
                "Symbol is required."
            )

        normalized_direction = self._direction(
            direction
        )

        requested_volume = self._decimal(
            volume,
            "volume",
        )

        signal_entry = self._decimal(
            signal_entry_price,
            "signal_entry_price",
        )

        requested_stop_loss = self._decimal(
            stop_loss,
            "stop_loss",
        )

        requested_take_profit = self._decimal(
            take_profit,
            "take_profit",
        )

        if requested_volume <= 0:
            raise MT5ExecutionError(
                "Volume must be greater than zero."
            )

        if signal_entry <= 0:
            raise MT5ExecutionError(
                "Signal entry price must be greater than zero."
            )

        if requested_stop_loss <= 0:
            raise MT5ExecutionError(
                "Stop loss must be greater than zero."
            )

        if requested_take_profit <= 0:
            raise MT5ExecutionError(
                "Take profit must be greater than zero."
            )

        if self.REQUIRE_EXPLICIT_EXECUTION and not confirmation:
            return MT5ExecutionResult(
                approved=False,
                status="confirmation_required",
                symbol=application_symbol,
                broker_symbol=None,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=None,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=None,
                signal_price_deviation_percent=None,
                errors=[
                    "Explicit final trade confirmation is required "
                    "before MT5 execution."
                ],
                execution_sent=False,
                message=(
                    "Trade execution blocked. "
                    "Final confirmation is required."
                ),
            )

        # ---------------------------------------------------------
        # FINAL BROKER VALIDATION
        # ---------------------------------------------------------

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
            return MT5ExecutionResult(
                approved=False,
                status="validation_error",
                symbol=application_symbol,
                broker_symbol=None,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=None,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=None,
                signal_price_deviation_percent=None,
                errors=[str(exc)],
                execution_sent=False,
                message=(
                    "Final broker validation failed."
                ),
            )

        if not validation.approved:
            return MT5ExecutionResult(
                approved=False,
                status="broker_validation_failed",
                symbol=application_symbol,
                broker_symbol=validation.broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=(
                    self._decimal(
                        validation.execution_price,
                        "execution_price",
                    )
                    if validation.execution_price is not None
                    else None
                ),
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=None,
                signal_price_deviation_percent=None,
                margin_required=(
                    self._decimal(
                        validation.margin_required,
                        "margin_required",
                    )
                    if validation.margin_required is not None
                    else None
                ),
                free_margin=(
                    self._decimal(
                        validation.free_margin,
                        "free_margin",
                    )
                    if validation.free_margin is not None
                    else None
                ),
                checks=validation.checks,
                warnings=validation.warnings,
                errors=validation.errors,
                execution_sent=False,
                message=(
                    "Final broker validation failed. "
                    "Order was not sent."
                ),
            )

        broker_symbol = validation.broker_symbol

        if not broker_symbol:
            return MT5ExecutionResult(
                approved=False,
                status="broker_symbol_missing",
                symbol=application_symbol,
                broker_symbol=None,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=None,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=None,
                signal_price_deviation_percent=None,
                errors=[
                    "Broker symbol could not be resolved."
                ],
                execution_sent=False,
                message=(
                    "Execution blocked because the broker "
                    "symbol could not be resolved."
                ),
            )

        # ---------------------------------------------------------
        # GET A SECOND FRESH TICK
        # ---------------------------------------------------------

        symbol_info = mt5_worker_manager.symbol_info(
            mt5_account_id=mt5_account_id,
            user_id=user_id,
            symbol=broker_symbol,
        )

        if symbol_info is None:
            return MT5ExecutionResult(
                approved=False,
                status="symbol_unavailable",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=None,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=None,
                signal_price_deviation_percent=None,
                errors=[
                    f"MT5 symbol info unavailable: {broker_symbol}"
                ],
                execution_sent=False,
                message=(
                    "Execution blocked because broker symbol "
                    "information is unavailable."
                ),
            )

        tick = mt5_worker_manager.symbol_info_tick(
            mt5_account_id=mt5_account_id,
            user_id=user_id,
            symbol=broker_symbol,
        )

        if tick is None:
            return MT5ExecutionResult(
                approved=False,
                status="tick_unavailable",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=None,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=None,
                signal_price_deviation_percent=None,
                errors=[
                    "Fresh broker tick could not be obtained."
                ],
                execution_sent=False,
                message=(
                    "Execution blocked because a fresh "
                    "broker price is unavailable."
                ),
            )

        ask_price = Decimal(str(tick.get("ask", 0) or 0))
        bid_price = Decimal(str(tick.get("bid", 0) or 0))

        if ask_price <= 0 or bid_price <= 0:
            return MT5ExecutionResult(
                approved=False,
                status="invalid_execution_price",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=None,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=None,
                signal_price_deviation_percent=None,
                errors=[
                    "Broker returned invalid bid/ask prices."
                ],
                execution_sent=False,
                message=(
                    "Execution blocked because the broker returned "
                    "invalid bid/ask prices."
                ),
            )

        tick_size = Decimal(
            str(
                symbol_info.get(
                    "trade_tick_size",
                    0,
                )
                or symbol_info.get(
                    "point",
                    0,
                )
                or "0.00000001"
            )
        )

        if tick_size <= 0:
            tick_size = Decimal("0.00000001")

        execution_mode, order_type_name = (
            self._classify_order_type(
                direction=normalized_direction,
                requested_entry=signal_entry,
                ask=ask_price,
                bid=bid_price,
                tolerance=tick_size,
            )
        )

        if execution_mode == "market":
            execution_price = (
                ask_price
                if normalized_direction == "buy"
                else bid_price
            )
        else:
            execution_price = signal_entry

        checks = list(validation.checks)
        warnings = list(validation.warnings)
        errors: list[str] = []

        checks.append(
            f"Entry classified as {order_type_name}"
        )

        if execution_mode == "pending":
            checks.append(
                "Requested entry will be used as the exact pending-order activation price"
            )
        else:
            checks.append(
                "Requested entry is effectively at market and will execute immediately"
            )

        if execution_price <= 0:
            return MT5ExecutionResult(
                approved=False,
                status="invalid_execution_price",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=execution_price,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=None,
                signal_price_deviation_percent=None,
                errors=[
                    "Broker returned an invalid executable price."
                ],
                execution_sent=False,
                message=(
                    "Execution blocked because the executable "
                    "price is invalid."
                ),
            )

        deviation, deviation_percent = (
            self._calculate_deviation(
                signal_entry,
                execution_price,
            )
        )

        checks.append(
            "Fresh execution tick received immediately before order submission"
        )

        if (
            execution_mode == "market"
            and deviation_percent
            > self.MAX_SIGNAL_PRICE_DEVIATION_PERCENT
        ):
            errors.append(
                "Signal entry price became stale during "
                "final execution validation."
            )

            warnings.append(
                "The market moved beyond the allowed execution "
                "deviation threshold."
            )

            return MT5ExecutionResult(
                approved=False,
                status="stale_signal",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=execution_price,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=deviation,
                signal_price_deviation_percent=deviation_percent,
                margin_required=(
                    self._decimal(
                        validation.margin_required,
                        "margin_required",
                    )
                    if validation.margin_required is not None
                    else None
                ),
                free_margin=(
                    self._decimal(
                        validation.free_margin,
                        "free_margin",
                    )
                    if validation.free_margin is not None
                    else None
                ),
                risk_amount=None,
                risk_percent=(
                    self._decimal(
                        risk_percent,
                        "risk_percent",
                    )
                    if risk_percent is not None
                    else None
                ),
                checks=checks,
                warnings=warnings,
                errors=errors,
                execution_sent=False,
                message=(
                    "Execution blocked because the signal became "
                    "stale before order submission."
                ),
            )

        checks.append(
            "Signal price remains within final execution deviation threshold"
        )

        # ---------------------------------------------------------
        # REFRESH ACCOUNT INFORMATION
        # ---------------------------------------------------------

        account_info = mt5_worker_manager.account_info(
                mt5_account_id=mt5_account_id,
                user_id=user_id,
            )

        if account_info is None:
            return MT5ExecutionResult(
                approved=False,
                status="account_unavailable",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=execution_price,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=deviation,
                signal_price_deviation_percent=deviation_percent,
                checks=checks,
                warnings=warnings,
                errors=[
                    "MT5 account information is unavailable."
                ],
                execution_sent=False,
                message=(
                    "Execution blocked because the MT5 account "
                    "could not be read."
                ),
            )

        free_margin = Decimal(
            str(
                account_info.get(
                    "margin_free",
                    0,
                )
                or 0
            )
        )

        if free_margin <= 0:
            return MT5ExecutionResult(
                approved=False,
                status="insufficient_free_margin",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=execution_price,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=deviation,
                signal_price_deviation_percent=deviation_percent,
                free_margin=free_margin,
                checks=checks,
                warnings=warnings,
                errors=[
                    "Free margin is not sufficient."
                ],
                execution_sent=False,
                message=(
                    "Execution blocked because free margin "
                    "is insufficient."
                ),
            )

        checks.append(
            "Fresh MT5 account margin information received"
        )

        # ---------------------------------------------------------
        # CALCULATE FINAL MARGIN
        # ---------------------------------------------------------

        order_type = self._mt5_order_type(
    direction=normalized_direction,
    execution_mode=execution_mode,
    order_type_name=order_type_name,
)

        # ---------------------------------------------------------
        # MT5 MARGIN ESTIMATION
        # ---------------------------------------------------------
        # MT5 may return 0.0 for order_calc_margin() when the
        # supplied order type is a pending order such as SELL_LIMIT.
        #
        # For risk/margin validation, calculate the equivalent
        # market-order margin instead. This estimates the margin
        # required for the position without changing the actual
        # pending order that will be submitted later.
        #
        # The actual execution request remains the original
        # pending order with the exact requested activation price.

        if execution_mode == "pending":
            margin_order_type = (
                "BUY"
                if normalized_direction == "buy"
                else "SELL"
            )

            margin_price = (
                ask_price
                if normalized_direction == "buy"
                else bid_price
            )


            checks.append(
                "Pending-order margin calculated using equivalent "
                "market-order margin"
            )
        else:
            margin_order_type = order_type
            margin_price = execution_price

        margin_result = mt5_worker_manager.order_calc_margin(
            mt5_account_id=mt5_account_id,
            user_id=user_id,
            request={
                "order_type": margin_order_type,
                "symbol": broker_symbol,
                "volume": float(requested_volume),
                "price": float(margin_price),
            },
        )

        margin_required_raw = (
            margin_result.get("margin")
            if isinstance(margin_result, dict)
            else None
        )

        margin_required = (
            Decimal(str(margin_required_raw))
            if margin_required_raw is not None
            else None
        )

        if margin_required is None:
            return MT5ExecutionResult(
                approved=False,
                status="margin_calculation_failed",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=execution_price,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=deviation,
                signal_price_deviation_percent=deviation_percent,
                free_margin=free_margin,
                checks=checks,
                warnings=warnings,
                errors=[
                    "MT5 could not calculate the required margin."
                ],
                execution_sent=False,
                message=(
                    "Execution blocked because required margin "
                    "could not be calculated."
                ),
            )

        if margin_required > free_margin:
            return MT5ExecutionResult(
                approved=False,
                status="insufficient_margin",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=execution_price,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=deviation,
                signal_price_deviation_percent=deviation_percent,
                margin_required=margin_required,
                free_margin=free_margin,
                checks=checks,
                warnings=warnings,
                errors=[
                    "Required margin exceeds available free margin."
                ],
                execution_sent=False,
                message=(
                    "Execution blocked because required margin "
                    "exceeds available free margin."
                ),
            )

        checks.append(
            "Final required margin is within available free margin"
        )

        # ---------------------------------------------------------
        # FINAL SYMBOL / VOLUME / PRECISION CHECK
        # ---------------------------------------------------------

        digits = int(
            symbol_info.get(
                "digits",
                0,
            )
            or 0
        )

        broker_volume_min = Decimal(
            str(
                symbol_info.get(
                    "volume_min",
                    0,
                )
                or 0
            )
        )

        broker_volume_max = Decimal(
            str(
                symbol_info.get(
                    "volume_max",
                    0,
                )
                or 0
            )
        )

        broker_volume_step = Decimal(
            str(
                symbol_info.get(
                    "volume_step",
                    0,
                )
                or 0
            )
        )

        if broker_volume_min > 0 and requested_volume < broker_volume_min:
            errors.append(
                "Requested volume is below broker minimum."
            )

        if broker_volume_max > 0 and requested_volume > broker_volume_max:
            errors.append(
                "Requested volume exceeds broker maximum."
            )

        if broker_volume_step > 0:
            steps = (
                requested_volume
                / broker_volume_step
            )

            if steps != steps.to_integral_value():
                errors.append(
                    "Requested volume does not match broker volume step."
                )

        if errors:
            return MT5ExecutionResult(
                approved=False,
                status="final_validation_failed",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=execution_price,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=deviation,
                signal_price_deviation_percent=deviation_percent,
                margin_required=margin_required,
                free_margin=free_margin,
                checks=checks,
                warnings=warnings,
                errors=errors,
                execution_sent=False,
                message=(
                    "Final execution validation failed. "
                    "Order was not sent."
                ),
            )

        # Normalize prices to broker precision.
        execution_price = execution_price.quantize(
            Decimal("1").scaleb(-digits)
        )

        requested_stop_loss = requested_stop_loss.quantize(
            Decimal("1").scaleb(-digits)
        )

        requested_take_profit = requested_take_profit.quantize(
            Decimal("1").scaleb(-digits)
        )

        # ---------------------------------------------------------
        # ---------------------------------------------------------
        # BUILD MT5 REQUEST
        # ---------------------------------------------------------

        if execution_mode == "pending":
            filling_mode = "RETURN"
            trade_action = "PENDING"
            request_price = signal_entry

            checks.append(
                "MT5 pending-order request constructed with RETURN filling"
            )
        else:
            filling_mode = self._select_filling_mode(
                symbol_info
            )
            trade_action = "DEAL"
            request_price = execution_price

            checks.append(
                "MT5 market-order request constructed"
            )

            trade_exemode = int(
                symbol_info.get(
                    "trade_exemode",
                    0,
                )
                or 0
            )

            checks.append(
                "MT5 symbol trade execution mode="
                f"{trade_exemode}; worker will apply broker execution rules"
            )

        request = {
            "action": trade_action,
            "symbol": broker_symbol,
            "volume": float(requested_volume),
            "type": order_type,
            "sl": float(requested_stop_loss),
            "tp": float(requested_take_profit),
            "deviation": 20,
            "magic": 202609,
            "comment": comment,
            "type_time": "GTC",
            "type_filling": filling_mode,
            "execution_mode": execution_mode,
            "price": float(request_price),
        }

        # FINAL PRE-SEND CHECK
        # ---------------------------------------------------------

        final_tick = mt5_worker_manager.symbol_info_tick(
            mt5_account_id=mt5_account_id,
            user_id=user_id,
            symbol=broker_symbol,
        )

        if final_tick is None:
            return MT5ExecutionResult(
                approved=False,
                status="final_tick_unavailable",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=execution_price,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=deviation,
                signal_price_deviation_percent=deviation_percent,
                margin_required=margin_required,
                free_margin=free_margin,
                checks=checks,
                warnings=warnings,
                errors=[
                    "Final tick disappeared immediately before execution."
                ],
                execution_sent=False,
                message=(
                    "Execution blocked because the final "
                    "market tick is unavailable."
                ),
            )

        if execution_mode == "pending":
            # Pending orders keep the user's requested activation price.
            final_execution_price = signal_entry
            final_deviation = None
            final_deviation_percent = None

            checks.append(
                "Pending entry price preserved exactly as requested"
            )
        else:
            final_execution_price = (
                Decimal(
                    str(
                        final_tick.get("ask", 0)
                        if normalized_direction == "buy"
                        else final_tick.get("bid", 0)
                    )
                )
            )

            final_deviation, final_deviation_percent = (
                self._calculate_deviation(
                    signal_entry,
                    final_execution_price,
                )
            )

        if (
            execution_mode == "market"
            and final_deviation_percent
            > self.MAX_SIGNAL_PRICE_DEVIATION_PERCENT
        ):
            return MT5ExecutionResult(
                approved=False,
                status="final_price_changed",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=final_execution_price,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=final_deviation,
                signal_price_deviation_percent=final_deviation_percent,
                margin_required=margin_required,
                free_margin=free_margin,
                checks=checks,
                warnings=warnings,
                errors=[
                    "Market price changed beyond the allowed "
                    "threshold immediately before execution."
                ],
                execution_sent=False,
                message=(
                    "Execution cancelled because the market "
                    "price changed immediately before submission."
                ),
            )

        if execution_mode == "market":
            if market_execution:
                request.pop("price", None)
                checks.append(
                    "Market Execution request remains price-less immediately before order_send"
                )
            else:
                request["price"] = float(
                    final_execution_price.quantize(
                        Decimal("1").scaleb(-digits)
                    )
                )
                checks.append(
                    "Final market price confirmed immediately before order_send"
                )
        else:
            request["price"] = float(
                signal_entry.quantize(
                    Decimal("1").scaleb(-digits)
                )
            )
            checks.append(
                "Pending activation price confirmed immediately before order_send"
            )

        # ---------------------------------------------------------
        # SEND ORDER
        # ---------------------------------------------------------

        # ---------------------------------------------------------
        # MT5 BROKER PREFLIGHT
        # ---------------------------------------------------------
        # order_check() validates the exact request with the broker
        # without sending the trade.
        logger.warning("MT5 PREFLIGHT REQUEST symbol=%s action=%s type=%s volume=%s price=%s sl=%s tp=%s filling=%s execution_mode=%s trade_exemode=%s", broker_symbol, request.get("action"), request.get("type"), request.get("volume"), request.get("price"), request.get("sl"), request.get("tp"), request.get("type_filling"), execution_mode, trade_exemode)
        try:
            preflight = mt5_worker_manager.order_check(
                mt5_account_id=mt5_account_id,
                user_id=user_id,
                request=request,
            )

        except MT5WorkerManagerError as exc:
            raise MT5ExecutionError(
                f"MT5 worker preflight failed: {exc}"
            ) from exc
        logger.warning(
            "MT5 PREFLIGHT RESULT %s",
            preflight,
        )

        if preflight is None:
            return MT5ExecutionResult(
                approved=False,
                status="preflight_failed",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=final_execution_price,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=final_deviation,
                signal_price_deviation_percent=final_deviation_percent,
                margin_required=margin_required,
                free_margin=free_margin,
                checks=checks,
                warnings=warnings,
                errors=[
                    "MT5 order_check returned no result "
                    "from worker process."
                ],
                execution_sent=False,
                message=(
                    "Execution blocked because MT5 broker "
                    "preflight returned no result."
                ),
            )

        preflight_retcode = (
            preflight.get("retcode")
            if isinstance(preflight, dict)
            else getattr(preflight, "retcode", None)
        )

        preflight_retcode_description = str(
            (
                preflight.get("retcode_description")
                if isinstance(preflight, dict)
                else getattr(
                    preflight,
                    "retcode_description",
                    "",
                )
            )
            or ""
        )

        preflight_comment = str(
            (
                preflight.get("comment")
                if isinstance(preflight, dict)
                else getattr(
                    preflight,
                    "comment",
                    "",
                )
            )
            or ""
        )

        preflight_accepted = bool(
            (
                preflight.get("accepted", False)
                if isinstance(preflight, dict)
                else getattr(
                    preflight,
                    "accepted",
                    False,
                )
            )
        )

        if not preflight_accepted:
            return MT5ExecutionResult(
                approved=False,
                status="preflight_failed",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=final_execution_price,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=final_deviation,
                signal_price_deviation_percent=final_deviation_percent,
                margin_required=margin_required,
                free_margin=free_margin,
                checks=checks,
                warnings=warnings,
                errors=[
                    "MT5 order_check failed: "
                    f"retcode={preflight_retcode}, "
                    f"description={preflight_retcode_description}, "
                    f"comment={preflight_comment}"
                ],
                execution_sent=False,
                message=(
                    "Execution blocked because the MT5 "
                    "broker preflight check failed."
                ),
            )

        checks.append(
            "MT5 order_check passed: "
            f"retcode={preflight_retcode}, "
            f"description={preflight_retcode_description}, "
            f"comment={preflight_comment}"
        )

        # ---------------------------------------------------------
        # SEND ORDER
        # ---------------------------------------------------------

        logger.warning(
            "MT5 ORDER_SEND REQUEST symbol=%s action=%s type=%s volume=%s price=%s sl=%s tp=%s filling=%s execution_mode=%s trade_exemode=%s",
            broker_symbol,
            request.get("action"),
            request.get("type"),
            request.get("volume"),
            request.get("price"),
            request.get("sl"),
            request.get("tp"),
            request.get("type_filling"),
            execution_mode,
            trade_exemode,
        )

        try:
            result = mt5_worker_manager.execute_order(
                mt5_account_id=mt5_account_id,
                user_id=user_id,
                request=request,
            )

        except MT5WorkerManagerError as exc:
            raise MT5ExecutionError(
                f"MT5 worker execution failed: {exc}"
            ) from exc

        logger.warning(
            "MT5 ORDER_SEND RESULT %s",
            result,
        )

        if isinstance(result, dict):
            class WorkerResult:
                pass

            worker_result = WorkerResult()

            for key, value in result.items():
                setattr(
                    worker_result,
                    key,
                    value,
                )

            result = worker_result

        if result is None:

            return MT5ExecutionResult(
                approved=False,
                status="order_send_failed",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=final_execution_price,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=final_deviation,
                signal_price_deviation_percent=final_deviation_percent,
                margin_required=margin_required,
                free_margin=free_margin,
                risk_amount=self._risk_amount(
                    mt5_account_id=mt5_account_id,
                    user_id=user_id,
                    broker_symbol=broker_symbol,
                    direction=normalized_direction,
                    execution_price=final_execution_price,
                    stop_loss=requested_stop_loss,
                    volume=requested_volume,
                ),
                risk_percent=(
                    self._decimal(
                        risk_percent,
                        "risk_percent",
                    )
                    if risk_percent is not None
                    else None
                ),
                checks=checks,
                warnings=warnings,
                errors=[
                    f"MT5 order_send returned no result: "
                    f"{error_code} - {error_message}"
                ],
                execution_sent=True,
                message=(
                    "MT5 order submission was attempted but "
                    "returned no result."
                ),
            )

        retcode = getattr(
            result,
            "retcode",
            None,
        )

        retcode_description = str(
            getattr(
                result,
                "retcode_description",
                "",
            )
            or ""
        )

        execution_accepted = bool(
            getattr(
                result,
                "accepted",
                False,
            )
        )

        order_ticket = getattr(
            result,
            "order",
            None,
        )

        deal_ticket = getattr(
            result,
            "deal",
            None,
        )

        execution_sent = True

        if not execution_accepted:
            return MT5ExecutionResult(
                approved=False,
                status="rejected_by_mt5",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                volume=requested_volume,
                requested_entry_price=signal_entry,
                execution_price=final_execution_price,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                signal_price_deviation=final_deviation,
                signal_price_deviation_percent=final_deviation_percent,
                order_ticket=(
                    int(order_ticket)
                    if order_ticket
                    else None
                ),
                deal_ticket=(
                    int(deal_ticket)
                    if deal_ticket
                    else None
                ),
                retcode=retcode,
                retcode_description=retcode_description,
                margin_required=margin_required,
                free_margin=free_margin,
                risk_amount=self._risk_amount(
                    mt5_account_id=mt5_account_id,
                    user_id=user_id,
                    broker_symbol=broker_symbol,
                    direction=normalized_direction,
                    execution_price=final_execution_price,
                    stop_loss=requested_stop_loss,
                    volume=requested_volume,
                ),
                risk_percent=(
                    self._decimal(
                        risk_percent,
                        "risk_percent",
                    )
                    if risk_percent is not None
                    else None
                ),
                checks=checks,
                warnings=warnings,
                errors=[
                    f"MT5 rejected the trade: "
                    f"{retcode_description}",
                    "MT5 worker returned broker rejection details.",
                ],
                execution_sent=execution_sent,
                message=(
                    "MT5 received the order request but "
                    "rejected the trade."
                ),
            )

        checks.append(
            "MT5 accepted the order request"
        )

        return MT5ExecutionResult(
            approved=True,
            status=(
                "pending_order_placed"
                if execution_mode == "pending"
                else "executed"
            ),
            symbol=application_symbol,
            broker_symbol=broker_symbol,
            direction=normalized_direction,
            volume=requested_volume,
            requested_entry_price=signal_entry,
            execution_price=(
                None
                if execution_mode == "pending"
                else final_execution_price
            ),
            execution_mode=execution_mode,
            order_type=order_type_name,
            pending_order_status=(
                "placed"
                if execution_mode == "pending"
                else "not_applicable"
            ),
            pending_order_placed_at=(
                __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat()
                if execution_mode == "pending"
                else None
            ),
            stop_loss=requested_stop_loss,
            take_profit=requested_take_profit,
            signal_price_deviation=final_deviation,
            signal_price_deviation_percent=final_deviation_percent,
            order_ticket=(
                int(order_ticket)
                if order_ticket
                else None
            ),
            deal_ticket=(
                int(deal_ticket)
                if deal_ticket
                else None
            ),
            retcode=retcode,
            retcode_description=retcode_description,
            margin_required=margin_required,
            free_margin=free_margin,
            risk_amount=self._risk_amount(
                mt5_account_id=mt5_account_id,
                user_id=user_id,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                execution_price=final_execution_price,
                stop_loss=requested_stop_loss,
                volume=requested_volume,
            ),
            risk_percent=(
                self._decimal(
                    risk_percent,
                    "risk_percent",
                )
                if risk_percent is not None
                else None
            ),
            checks=checks,
            warnings=warnings,
            errors=[],
            execution_sent=True,
            message=(
                "Pending order placed successfully through MetaTrader 5."
                if execution_mode == "pending"
                else "Trade executed successfully through MetaTrader 5."
            ),
        )


mt5_execution_service = MT5ExecutionService()





