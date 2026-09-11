from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import MetaTrader5 as mt5

from app.services.broker_validation_service import (
    BrokerValidationError,
    broker_validation_service,
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
    This is the ONLY service in this stage that is allowed
    to call mt5.order_send().

    The service performs fresh broker validation immediately
    before sending the order.
    """

    MAX_SIGNAL_PRICE_DEVIATION_PERCENT = Decimal("0.25")

    # Safety requirement:
    # MT5 execution requires an explicitly enabled execution request.
    REQUIRE_EXPLICIT_EXECUTION = True

    def __init__(self) -> None:
        self.broker_validation = broker_validation_service

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
    def _retcode_description(retcode: int) -> str:
        descriptions = {
            getattr(mt5, "TRADE_RETCODE_DONE", -1):
                "Request completed successfully",

            getattr(mt5, "TRADE_RETCODE_PLACED", -1):
                "Order placed successfully",

            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", -1):
                "Request partially completed",

            getattr(mt5, "TRADE_RETCODE_REQUOTE", -1):
                "Requote",

            getattr(mt5, "TRADE_RETCODE_REJECT", -1):
                "Request rejected",

            getattr(mt5, "TRADE_RETCODE_CANCEL", -1):
                "Request cancelled",

            getattr(mt5, "TRADE_RETCODE_INVALID", -1):
                "Invalid request",

            getattr(mt5, "TRADE_RETCODE_INVALID_VOLUME", -1):
                "Invalid volume",

            getattr(mt5, "TRADE_RETCODE_INVALID_PRICE", -1):
                "Invalid price",

            getattr(mt5, "TRADE_RETCODE_INVALID_STOPS", -1):
                "Invalid stops",

            getattr(mt5, "TRADE_RETCODE_TRADE_DISABLED", -1):
                "Trading disabled",

            getattr(mt5, "TRADE_RETCODE_MARKET_CLOSED", -1):
                "Market closed",

            getattr(mt5, "TRADE_RETCODE_NO_MONEY", -1):
                "Insufficient money",

            getattr(mt5, "TRADE_RETCODE_PRICE_CHANGED", -1):
                "Price changed",

            getattr(mt5, "TRADE_RETCODE_PRICE_OFF", -1):
                "No price available",

            getattr(mt5, "TRADE_RETCODE_INVALID_FILL", -1):
                "Invalid filling mode",
        }

        return descriptions.get(
            retcode,
            f"MT5 returned retcode {retcode}",
        )

    @staticmethod
    def _risk_amount(
        *,
        broker_symbol: str,
        direction: str,
        execution_price: Decimal,
        stop_loss: Decimal,
        volume: Decimal,
    ) -> Optional[Decimal]:

        symbol_info = mt5.symbol_info(broker_symbol)

        if symbol_info is None:
            return None

        tick_size = Decimal(
            str(
                getattr(
                    symbol_info,
                    "trade_tick_size",
                    0,
                )
                or 0
            )
        )

        tick_value = Decimal(
            str(
                getattr(
                    symbol_info,
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
    ) -> int:

        filling_mode = int(
            getattr(
                symbol_info,
                "filling_mode",
                0,
            )
            or 0
        )

        # The broker validation service has already confirmed
        # the broker filling mode. Use it directly.
        if filling_mode:
            return filling_mode

        # Fallback to IOC if the broker reports no explicit mode.
        return getattr(
            mt5,
            "ORDER_FILLING_IOC",
            1,
        )

    def execute(
        self,
        *,
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
            validation = self.broker_validation.validate(
                symbol=application_symbol,
                direction=normalized_direction,
                entry_price=signal_entry,
                stop_loss=requested_stop_loss,
                take_profit=requested_take_profit,
                volume=requested_volume,
            )

        except BrokerValidationError as exc:
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

        symbol_info = mt5.symbol_info(
            broker_symbol
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

        tick = mt5.symbol_info_tick(
            broker_symbol
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

        if normalized_direction == "buy":
            execution_price = Decimal(
                str(tick.ask)
            )
        else:
            execution_price = Decimal(
                str(tick.bid)
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

        checks = list(validation.checks)
        warnings = list(validation.warnings)
        errors: list[str] = []

        checks.append(
            "Fresh execution tick received immediately before order submission"
        )

        if (
            deviation_percent
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

        account_info = mt5.account_info()

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
                getattr(
                    account_info,
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

        order_type = (
            mt5.ORDER_TYPE_BUY
            if normalized_direction == "buy"
            else mt5.ORDER_TYPE_SELL
        )

        margin_required_raw = (
            mt5.order_calc_margin(
                order_type,
                broker_symbol,
                float(requested_volume),
                float(execution_price),
            )
        )

        margin_required = (
            Decimal(str(margin_required_raw))
            if margin_required_raw is not None
            else None
        )

        if (
            margin_required is None
            or margin_required <= 0
        ):
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
            getattr(
                symbol_info,
                "digits",
                0,
            )
            or 0
        )

        broker_volume_min = Decimal(
            str(
                getattr(
                    symbol_info,
                    "volume_min",
                    0,
                )
                or 0
            )
        )

        broker_volume_max = Decimal(
            str(
                getattr(
                    symbol_info,
                    "volume_max",
                    0,
                )
                or 0
            )
        )

        broker_volume_step = Decimal(
            str(
                getattr(
                    symbol_info,
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
        # BUILD MT5 REQUEST
        # ---------------------------------------------------------

        filling_mode = self._select_filling_mode(
            symbol_info
        )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": broker_symbol,
            "volume": float(requested_volume),
            "type": order_type,
            "price": float(execution_price),
            "sl": float(requested_stop_loss),
            "tp": float(requested_take_profit),
            "deviation": 20,
            "magic": 20260903,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        checks.append(
            "MT5 market-order request constructed"
        )

        # ---------------------------------------------------------
        # FINAL PRE-SEND CHECK
        # ---------------------------------------------------------

        final_tick = mt5.symbol_info_tick(
            broker_symbol
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

        final_execution_price = (
            Decimal(
                str(
                    final_tick.ask
                    if normalized_direction == "buy"
                    else final_tick.bid
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
            final_deviation_percent
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

        # Use the freshest price in the actual request.
        request["price"] = float(
            final_execution_price.quantize(
                Decimal("1").scaleb(-digits)
            )
        )

        checks.append(
            "Final market price confirmed immediately before order_send"
        )

        # ---------------------------------------------------------
        # SEND ORDER
        # ---------------------------------------------------------

        # ---------------------------------------------------------
        # MT5 BROKER PREFLIGHT
        # ---------------------------------------------------------
        # order_check() validates the exact request with the broker
        # without sending the trade.
        preflight = mt5.order_check(request)

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
                    "MT5 order_check returned no result: "
                    f"{mt5.last_error()}"
                ],
                execution_sent=False,
                message=(
                    "Execution blocked because MT5 broker "
                    "preflight returned no result."
                ),
            )

        preflight_retcode = int(
            getattr(preflight, "retcode", 0) or 0
        )

        preflight_comment = str(
            getattr(preflight, "comment", "") or ""
        )

        if preflight_retcode != 0:
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
            f"comment={preflight_comment}"
        )

        # ---------------------------------------------------------
        # SEND ORDER
        # ---------------------------------------------------------

        result = mt5.order_send(
            request
        )

        if result is None:
            error_code, error_message = (
                mt5.last_error()
            )

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

        retcode = int(
            getattr(
                result,
                "retcode",
                0,
            )
            or 0
        )

        retcode_description = (
            self._retcode_description(
                retcode
            )
        )

        success_codes = {
            getattr(
                mt5,
                "TRADE_RETCODE_DONE",
                -1,
            ),
            getattr(
                mt5,
                "TRADE_RETCODE_PLACED",
                -1,
            ),
            getattr(
                mt5,
                "TRADE_RETCODE_DONE_PARTIAL",
                -1,
            ),
        }

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

        if retcode not in success_codes:
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
                    f"{retcode_description}"
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
            status="executed",
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
                "Trade executed successfully through MetaTrader 5."
            ),
        )


mt5_execution_service = MT5ExecutionService()