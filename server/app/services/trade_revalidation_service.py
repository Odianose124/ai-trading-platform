from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.services.mt5_trade_setup_service import (
    mt5_trade_setup_service,
    MT5TradeSetupError,
)
from app.services.position_size_service import (
    position_size_service,
)
from app.services.broker_validation_service import (
    broker_validation_service,
    BrokerValidationError,
)


class TradeRevalidationError(Exception):
    """Raised when trade revalidation cannot be completed safely."""


@dataclass
class TradeRevalidationResult:
    approved: bool
    status: str

    intent_id: Optional[int]
    symbol: str
    direction: str

    original_signal_entry_price: Optional[Decimal]
    current_execution_price: Optional[Decimal]

    entry_price: Optional[Decimal]
    entry_zone: dict[str, Any] = field(default_factory=dict)

    stop_loss: Optional[Decimal] = None
    take_profit_1: Optional[Decimal] = None
    take_profit_2: Optional[Decimal] = None

    volume: Optional[Decimal] = None
    risk_percent: Optional[Decimal] = None

    risk_reward_1: Optional[Decimal] = None
    risk_reward_2: Optional[Decimal] = None

    broker_symbol: Optional[str] = None

    signal_price_deviation: Optional[Decimal] = None
    signal_price_deviation_percent: Optional[Decimal] = None

    setup_quality: Optional[str] = None
    market_bias: Optional[str] = None

    checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    message: str = ""

    revalidated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def serialize(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "status": self.status,
            "intent_id": self.intent_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "original_signal_entry_price": (
                str(self.original_signal_entry_price)
                if self.original_signal_entry_price is not None
                else None
            ),
            "current_execution_price": (
                str(self.current_execution_price)
                if self.current_execution_price is not None
                else None
            ),
            "entry_price": (
                str(self.entry_price)
                if self.entry_price is not None
                else None
            ),
            "entry_zone": self.entry_zone,
            "stop_loss": (
                str(self.stop_loss)
                if self.stop_loss is not None
                else None
            ),
            "take_profit_1": (
                str(self.take_profit_1)
                if self.take_profit_1 is not None
                else None
            ),
            "take_profit_2": (
                str(self.take_profit_2)
                if self.take_profit_2 is not None
                else None
            ),
            "volume": (
                str(self.volume)
                if self.volume is not None
                else None
            ),
            "risk_percent": (
                str(self.risk_percent)
                if self.risk_percent is not None
                else None
            ),
            "risk_reward_1": (
                str(self.risk_reward_1)
                if self.risk_reward_1 is not None
                else None
            ),
            "risk_reward_2": (
                str(self.risk_reward_2)
                if self.risk_reward_2 is not None
                else None
            ),
            "broker_symbol": self.broker_symbol,
            "signal_price_deviation": (
                str(self.signal_price_deviation)
                if self.signal_price_deviation is not None
                else None
            ),
            "signal_price_deviation_percent": (
                str(self.signal_price_deviation_percent)
                if self.signal_price_deviation_percent is not None
                else None
            ),
            "setup_quality": self.setup_quality,
            "market_bias": self.market_bias,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "reasons": self.reasons,
            "message": self.message,
            "revalidated_at": self.revalidated_at.isoformat(),
        }


class TradeRevalidationService:
    """
    Revalidates a previously generated trade intent against the
    current live MT5 market.

    Safety rules:

    1. A stale signal is never silently executed.
    2. Original SL/TP values never override a fresh structural setup.
    3. Fresh SL/TP values must come from fresh market analysis.
    4. Position size is recalculated from the fresh stop loss.
    5. Broker precision and constraints are respected.
    6. Final broker validation is performed before the trade can
       proceed to execution.
    7. This service never calls mt5.order_send().
    """

    MAX_SIGNAL_DEVIATION_PERCENT = Decimal("0.25")

    DEFAULT_RISK_PERCENT = Decimal("1.00")
    MAX_RISK_PERCENT = Decimal("2.00")

    def _decimal(
        self,
        value: Any,
        field_name: str,
    ) -> Decimal:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise TradeRevalidationError(
                f"{field_name} must be a valid number."
            ) from exc

        if not result.is_finite():
            raise TradeRevalidationError(
                f"{field_name} must be finite."
            )

        return result

    def _normalize_direction(
        self,
        direction: str,
    ) -> str:
        value = str(direction).strip().lower()

        if value in {"buy", "long"}:
            return "buy"

        if value in {"sell", "short"}:
            return "sell"

        raise TradeRevalidationError(
            f"Unsupported trade direction: {direction}"
        )

    def _calculate_deviation(
        self,
        signal_price: Decimal,
        execution_price: Decimal,
    ) -> tuple[Decimal, Decimal]:
        if signal_price <= 0:
            raise TradeRevalidationError(
                "Signal entry price must be greater than zero."
            )

        deviation = abs(
            execution_price - signal_price
        )

        deviation_percent = (
            deviation / signal_price
        ) * Decimal("100")

        return deviation, deviation_percent

    def _round_to_digits(
        self,
        value: Any,
        digits: int,
        field_name: str = "price",
    ) -> Decimal:
        """
        Round a price to the exact number of decimal places
        accepted by the broker.
        """
        price = self._decimal(
            value,
            field_name,
        )

        if digits < 0:
            raise TradeRevalidationError(
                "Broker price digits cannot be negative."
            )

        quantum = Decimal("1").scaleb(-digits)

        return price.quantize(
            quantum
        )

    def _round_zone(
        self,
        zone: dict[str, Any],
        digits: int,
    ) -> dict[str, Any]:
        """
        Normalize numeric entry-zone values to broker precision
        without modifying non-numeric diagnostic fields.
        """
        if not isinstance(zone, dict):
            return {}

        rounded: dict[str, Any] = {}

        for key, value in zone.items():
            if value is None:
                rounded[key] = value
                continue

            try:
                numeric_value = Decimal(str(value))

                if numeric_value.is_finite():
                    rounded[key] = str(
                        self._round_to_digits(
                            numeric_value,
                            digits,
                            f"entry zone {key}",
                        )
                    )
                else:
                    rounded[key] = value

            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                rounded[key] = value

        return rounded

    def _extract_setup_value(
        self,
        setup: Any,
        name: str,
        default: Any = None,
    ) -> Any:
        if setup is None:
            return default

        if isinstance(setup, dict):
            return setup.get(
                name,
                default,
            )

        return getattr(
            setup,
            name,
            default,
        )

    def _extract_setup_zone(
        self,
        setup: Any,
    ) -> dict[str, Any]:
        zone = self._extract_setup_value(
            setup,
            "entry_zone",
            {},
        )

        if isinstance(zone, dict):
            return zone

        return {}

    def _result_from_validation_failure(
        self,
        *,
        status: str,
        intent_id: Optional[int],
        symbol: str,
        direction: str,
        signal_price: Decimal,
        execution_price: Optional[Decimal],
        entry_price: Optional[Decimal],
        entry_zone: dict[str, Any],
        stop_loss: Optional[Decimal],
        take_profit_1: Optional[Decimal],
        take_profit_2: Optional[Decimal],
        volume: Optional[Decimal],
        risk_percent: Decimal,
        risk_reward_1: Optional[Decimal],
        risk_reward_2: Optional[Decimal],
        broker_symbol: Optional[str],
        setup_quality: Optional[str],
        market_bias: Optional[str],
        checks: list[str],
        warnings: list[str],
        errors: list[str],
        reasons: list[str],
        message: str,
    ) -> TradeRevalidationResult:

        deviation = None
        deviation_percent = None

        if (
            execution_price is not None
            and signal_price > 0
        ):
            deviation, deviation_percent = (
                self._calculate_deviation(
                    signal_price,
                    execution_price,
                )
            )

        return TradeRevalidationResult(
            approved=False,
            status=status,
            intent_id=intent_id,
            symbol=symbol,
            direction=direction,
            original_signal_entry_price=signal_price,
            current_execution_price=execution_price,
            entry_price=entry_price,
            entry_zone=entry_zone,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            volume=volume,
            risk_percent=risk_percent,
            risk_reward_1=risk_reward_1,
            risk_reward_2=risk_reward_2,
            broker_symbol=broker_symbol,
            signal_price_deviation=deviation,
            signal_price_deviation_percent=deviation_percent,
            setup_quality=setup_quality,
            market_bias=market_bias,
            checks=checks,
            warnings=warnings,
            errors=errors,
            reasons=reasons,
            message=message,
        )

    def revalidate(
        self,
        *,
        intent_id: Optional[int],
        symbol: str,
        direction: str,
        original_signal_entry_price: Any,
        original_stop_loss: Any = None,
        original_take_profit: Any = None,
        risk_percent: Any = None,
        volume: Any = None,
        timeframe: str = "15m",
        limit: int = 500,
        strength: int = 2,
        lookback: int = 20,
        minimum_touches: int = 2,
    ) -> TradeRevalidationResult:

        symbol = str(symbol).strip().upper()

        checks: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []
        reasons: list[str] = []

        try:
            direction = self._normalize_direction(
                direction
            )

        except TradeRevalidationError as exc:
            return TradeRevalidationResult(
                approved=False,
                status="invalid_request",
                intent_id=intent_id,
                symbol=symbol,
                direction=str(direction),
                original_signal_entry_price=None,
                current_execution_price=None,
                entry_price=None,
                checks=checks,
                warnings=warnings,
                errors=[str(exc)],
                reasons=reasons,
                message=(
                    "Trade revalidation failed because "
                    "the trade direction is invalid."
                ),
            )

        if not symbol:
            return TradeRevalidationResult(
                approved=False,
                status="invalid_request",
                intent_id=intent_id,
                symbol=symbol,
                direction=direction,
                original_signal_entry_price=None,
                current_execution_price=None,
                entry_price=None,
                checks=checks,
                warnings=warnings,
                errors=["Symbol is required."],
                reasons=reasons,
                message=(
                    "Trade revalidation failed because "
                    "symbol is missing."
                ),
            )

        signal_price: Optional[Decimal] = None
        requested_risk: Optional[Decimal] = None

        try:
            # =========================================================
            # 1. Validate request parameters
            # =========================================================

            signal_price = self._decimal(
                original_signal_entry_price,
                "original_signal_entry_price",
            )

            requested_risk = (
                self._decimal(
                    risk_percent,
                    "risk_percent",
                )
                if risk_percent is not None
                else self.DEFAULT_RISK_PERCENT
            )

            if signal_price <= 0:
                raise TradeRevalidationError(
                    "Original signal entry price must be greater than zero."
                )

            if requested_risk <= 0:
                raise TradeRevalidationError(
                    "Risk percent must be greater than zero."
                )

            if requested_risk > self.MAX_RISK_PERCENT:
                raise TradeRevalidationError(
                    f"Risk percent cannot exceed "
                    f"{self.MAX_RISK_PERCENT}%."
                )

            checks.append(
                "Revalidation request parameters verified"
            )

            # =========================================================
            # 2. Generate a completely fresh structural setup
            # =========================================================

            fresh_setup = mt5_trade_setup_service.analyze(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                strength=strength,
                lookback=lookback,
                minimum_touches=minimum_touches,
            )

            checks.append(
                "Fresh MT5 trade setup generated from current market data"
            )

            setup_bias = str(
                self._extract_setup_value(
                    fresh_setup,
                    "overall_bias",
                    self._extract_setup_value(
                        fresh_setup,
                        "market_bias",
                        "",
                    ),
                )
            ).strip().lower()

            setup_status = str(
                self._extract_setup_value(
                    fresh_setup,
                    "status",
                    "",
                )
            ).strip().lower()

            fresh_entry_raw = self._extract_setup_value(
                fresh_setup,
                "entry_price",
            )

            fresh_sl_raw = self._extract_setup_value(
                fresh_setup,
                "stop_loss",
            )

            fresh_tp1_raw = self._extract_setup_value(
                fresh_setup,
                "take_profit_1",
            )

            fresh_tp2_raw = self._extract_setup_value(
                fresh_setup,
                "take_profit_2",
            )

            fresh_rr1_raw = self._extract_setup_value(
                fresh_setup,
                "risk_reward_1",
            )

            fresh_rr2_raw = self._extract_setup_value(
                fresh_setup,
                "risk_reward_2",
            )

            fresh_quality = self._extract_setup_value(
                fresh_setup,
                "setup_quality",
            )

            fresh_zone = self._extract_setup_zone(
                fresh_setup
            )

            # =========================================================
            # 3. Verify fresh directional bias
            # =========================================================

            expected_bias = (
                "bullish"
                if direction == "buy"
                else "bearish"
            )

            if setup_bias and setup_bias != expected_bias:
                errors.append(
                    f"Fresh market bias is {setup_bias}, "
                    f"not {expected_bias}."
                )

            if setup_status in {
                "no_trade",
                "rejected",
                "invalid",
                "poor",
            }:
                errors.append(
                    "Fresh trade setup is not executable."
                )

            if fresh_entry_raw is None:
                errors.append(
                    "Fresh setup did not produce a valid entry price."
                )

            if fresh_sl_raw is None:
                errors.append(
                    "Fresh setup did not produce a valid stop loss."
                )

            if fresh_tp1_raw is None:
                errors.append(
                    "Fresh setup did not produce take profit 1."
                )

            if fresh_tp2_raw is None:
                errors.append(
                    "Fresh setup did not produce take profit 2."
                )

            if errors:
                return TradeRevalidationResult(
                    approved=False,
                    status="revalidation_failed",
                    intent_id=intent_id,
                    symbol=symbol,
                    direction=direction,
                    original_signal_entry_price=signal_price,
                    current_execution_price=None,
                    entry_price=None,
                    entry_zone=fresh_zone,
                    risk_percent=requested_risk,
                    setup_quality=fresh_quality,
                    market_bias=setup_bias or None,
                    checks=checks,
                    warnings=warnings,
                    errors=errors,
                    reasons=[
                        "Fresh market structure no longer supports "
                        "the requested trade direction."
                    ],
                    message=(
                        "Trade revalidation rejected the trade because "
                        "the fresh setup is no longer valid."
                    ),
                )

            fresh_entry = self._decimal(
                fresh_entry_raw,
                "fresh entry price",
            )

            fresh_sl = self._decimal(
                fresh_sl_raw,
                "fresh stop loss",
            )

            fresh_tp1 = self._decimal(
                fresh_tp1_raw,
                "fresh take profit 1",
            )

            fresh_tp2 = self._decimal(
                fresh_tp2_raw,
                "fresh take profit 2",
            )

            fresh_rr1 = (
                self._decimal(
                    fresh_rr1_raw,
                    "risk reward 1",
                )
                if fresh_rr1_raw is not None
                else None
            )

            fresh_rr2 = (
                self._decimal(
                    fresh_rr2_raw,
                    "risk reward 2",
                )
                if fresh_rr2_raw is not None
                else None
            )

            checks.append(
                "Fresh entry, stop loss and take profit levels verified"
            )

            # =========================================================
            # 4. Preliminary broker validation
            #
            # This validation is used to discover:
            # - broker symbol
            # - current executable price
            # - broker digits
            # - broker trading constraints
            #
            # The fresh setup prices are initially passed through the
            # existing broker validator. If it succeeds, we obtain
            # the broker precision and normalize all prices.
            # =========================================================

            preliminary_validation = (
                broker_validation_service.validate(
                    symbol=symbol,
                    direction=direction,
                    entry_price=fresh_entry,
                    stop_loss=fresh_sl,
                    take_profit=fresh_tp1,
                    volume=volume,
                )
            )

            current_execution_price = (
                self._decimal(
                    preliminary_validation.execution_price,
                    "current execution price",
                )
                if preliminary_validation.execution_price
                is not None
                else None
            )

            broker_symbol = (
                preliminary_validation.broker_symbol
            )

            # ---------------------------------------------------------
            # Calculate original signal deviation immediately.
            # This fixes the previous issue where deviation remained
            # None whenever broker validation failed.
            # ---------------------------------------------------------

            signal_deviation = None
            signal_deviation_percent = None

            if current_execution_price is not None:
                signal_deviation, signal_deviation_percent = (
                    self._calculate_deviation(
                        signal_price,
                        current_execution_price,
                    )
                )

            # =========================================================
            # 5. Obtain broker precision
            # =========================================================

            broker_digits = getattr(
                preliminary_validation,
                "digits",
                None,
            )

            if broker_digits is None:
                raise TradeRevalidationError(
                    "Broker validation did not return price precision."
                )

            broker_digits = int(broker_digits)

            checks.append(
                f"Broker price precision discovered: "
                f"{broker_digits} decimal places"
            )

            # =========================================================
            # 6. Normalize fresh prices to broker precision
            # =========================================================

            fresh_entry = self._round_to_digits(
                fresh_entry,
                broker_digits,
                "fresh entry price",
            )

            fresh_sl = self._round_to_digits(
                fresh_sl,
                broker_digits,
                "fresh stop loss",
            )

            fresh_tp1 = self._round_to_digits(
                fresh_tp1,
                broker_digits,
                "fresh take profit 1",
            )

            fresh_tp2 = self._round_to_digits(
                fresh_tp2,
                broker_digits,
                "fresh take profit 2",
            )

            fresh_zone = self._round_zone(
                fresh_zone,
                broker_digits,
            )

            checks.append(
                "Fresh entry, stop loss and take profit levels "
                "normalized to broker precision"
            )

            # =========================================================
            # 7. Handle preliminary broker validation failure
            #
            # If the failure was simply caused by precision, the
            # normalized prices above allow us to validate correctly.
            # If it was a genuine broker constraint failure, we reject.
            # =========================================================

            if not preliminary_validation.approved:

                preliminary_errors = list(
                    preliminary_validation.errors
                )

                precision_only_errors = all(
                    "precision" in str(error).lower()
                    or "decimal place" in str(error).lower()
                    for error in preliminary_errors
                )

                if preliminary_errors and not precision_only_errors:
                    return TradeRevalidationResult(
                        approved=False,
                        status="broker_validation_failed",
                        intent_id=intent_id,
                        symbol=symbol,
                        direction=direction,
                        original_signal_entry_price=signal_price,
                        current_execution_price=current_execution_price,
                        entry_price=fresh_entry,
                        entry_zone=fresh_zone,
                        stop_loss=fresh_sl,
                        take_profit_1=fresh_tp1,
                        take_profit_2=fresh_tp2,
                        volume=(
                            self._decimal(
                                volume,
                                "volume",
                            )
                            if volume is not None
                            else None
                        ),
                        risk_percent=requested_risk,
                        risk_reward_1=fresh_rr1,
                        risk_reward_2=fresh_rr2,
                        broker_symbol=broker_symbol,
                        setup_quality=fresh_quality,
                        market_bias=setup_bias or None,
                        signal_price_deviation=signal_deviation,
                        signal_price_deviation_percent=(
                            signal_deviation_percent
                        ),
                        checks=(
                            checks
                            + preliminary_validation.checks
                        ),
                        warnings=(
                            warnings
                            + preliminary_validation.warnings
                        ),
                        errors=preliminary_errors,
                        reasons=reasons,
                        message=(
                            "Fresh trade setup was generated, but "
                            "broker validation rejected the current "
                            "market state."
                        ),
                    )

                warnings.extend(
                    preliminary_validation.warnings
                )

            # =========================================================
            # 8. Fresh broker validation using normalized prices
            # =========================================================

            normalized_validation = (
                broker_validation_service.validate(
                    symbol=symbol,
                    direction=direction,
                    entry_price=fresh_entry,
                    stop_loss=fresh_sl,
                    take_profit=fresh_tp1,
                    volume=volume,
                )
            )

            if not normalized_validation.approved:
                return TradeRevalidationResult(
                    approved=False,
                    status="broker_validation_failed",
                    intent_id=intent_id,
                    symbol=symbol,
                    direction=direction,
                    original_signal_entry_price=signal_price,
                    current_execution_price=(
                        self._decimal(
                            normalized_validation.execution_price,
                            "current execution price",
                        )
                        if normalized_validation.execution_price
                        is not None
                        else current_execution_price
                    ),
                    entry_price=fresh_entry,
                    entry_zone=fresh_zone,
                    stop_loss=fresh_sl,
                    take_profit_1=fresh_tp1,
                    take_profit_2=fresh_tp2,
                    volume=(
                        self._decimal(
                            volume,
                            "volume",
                        )
                        if volume is not None
                        else None
                    ),
                    risk_percent=requested_risk,
                    risk_reward_1=fresh_rr1,
                    risk_reward_2=fresh_rr2,
                    broker_symbol=(
                        normalized_validation.broker_symbol
                        or broker_symbol
                    ),
                    setup_quality=fresh_quality,
                    market_bias=setup_bias or None,
                    signal_price_deviation=signal_deviation,
                    signal_price_deviation_percent=(
                        signal_deviation_percent
                    ),
                    checks=(
                        checks
                        + normalized_validation.checks
                    ),
                    warnings=(
                        warnings
                        + normalized_validation.warnings
                    ),
                    errors=normalized_validation.errors,
                    reasons=reasons,
                    message=(
                        "Fresh trade setup was generated, but "
                        "normalized broker validation rejected it."
                    ),
                )

            checks.extend(
                normalized_validation.checks
            )

            warnings.extend(
                normalized_validation.warnings
            )

            current_execution_price = self._decimal(
                normalized_validation.execution_price,
                "current execution price",
            )

            broker_symbol = (
                normalized_validation.broker_symbol
                or broker_symbol
            )

            # =========================================================
            # 9. Recalculate original signal deviation against the
            # current executable price.
            # =========================================================

            signal_deviation, signal_deviation_percent = (
                self._calculate_deviation(
                    signal_price,
                    current_execution_price,
                )
            )

            checks.append(
                "Original signal deviation calculated against "
                "current broker execution price"
            )

            if (
                signal_deviation_percent
                > self.MAX_SIGNAL_DEVIATION_PERCENT
            ):
                warnings.append(
                    "Original signal price is stale relative to "
                    "the current executable market price."
                )

                reasons.append(
                    "Original signal price exceeded the permitted "
                    "execution deviation."
                )

            else:
                checks.append(
                    "Original signal remains within permitted "
                    "execution deviation"
                )

            # =========================================================
            # 10. Original SL/TP are informational only
            #
            # Fresh structural levels always win.
            # =========================================================

            if original_stop_loss is not None:
                old_sl = self._decimal(
                    original_stop_loss,
                    "original_stop_loss",
                )

                old_sl_normalized = self._round_to_digits(
                    old_sl,
                    broker_digits,
                    "original stop loss",
                )

                if old_sl_normalized != fresh_sl:
                    warnings.append(
                        "Original stop loss differs from the fresh "
                        "structural stop. Fresh stop loss will be used."
                    )

            if original_take_profit is not None:
                old_tp = self._decimal(
                    original_take_profit,
                    "original_take_profit",
                )

                old_tp_normalized = self._round_to_digits(
                    old_tp,
                    broker_digits,
                    "original take profit",
                )

                if old_tp_normalized != fresh_tp1:
                    warnings.append(
                        "Original take profit differs from the fresh "
                        "structural target. Fresh take profit will be used."
                    )

            checks.append(
                "Original SL/TP cannot override fresh structural levels"
            )

            # =========================================================
            # 11. Recalculate position size from fresh setup
            # =========================================================

            sizing = position_size_service.calculate(
                symbol=symbol,
                direction=direction,
                entry_price=fresh_entry,
                stop_loss=fresh_sl,
                risk_percent=requested_risk,
            )

            if not bool(sizing.get("approved", False)):
                return TradeRevalidationResult(
                    approved=False,
                    status="position_size_failed",
                    intent_id=intent_id,
                    symbol=symbol,
                    direction=direction,
                    original_signal_entry_price=signal_price,
                    current_execution_price=current_execution_price,
                    entry_price=fresh_entry,
                    entry_zone=fresh_zone,
                    stop_loss=fresh_sl,
                    take_profit_1=fresh_tp1,
                    take_profit_2=fresh_tp2,
                    risk_percent=requested_risk,
                    risk_reward_1=fresh_rr1,
                    risk_reward_2=fresh_rr2,
                    broker_symbol=broker_symbol,
                    setup_quality=fresh_quality,
                    market_bias=setup_bias or None,
                    signal_price_deviation=signal_deviation,
                    signal_price_deviation_percent=(
                        signal_deviation_percent
                    ),
                    checks=checks,
                    warnings=warnings,
                    errors=(
                        list(sizing.get("errors", []))
                        if isinstance(sizing, dict)
                        else (list(getattr(sizing, "errors", [])) or ["Position sizing failed."])
                    ),
                    reasons=reasons,
                    message=(
                        "Fresh setup is valid, but position sizing "
                        "failed against current broker conditions."
                    ),
                )

            fresh_volume = self._extract_setup_value(
                sizing,
                "volume",
            )

            if fresh_volume is None:
                raise TradeRevalidationError(
                    "Position sizing did not return a volume."
                )

            fresh_volume = self._decimal(
                fresh_volume,
                "fresh volume",
            )

            checks.append(
                "Position size recalculated from fresh stop loss"
            )

            # =========================================================
            # 12. Final broker validation
            # =========================================================

            final_validation = (
                broker_validation_service.validate(
                    symbol=symbol,
                    direction=direction,
                    entry_price=fresh_entry,
                    stop_loss=fresh_sl,
                    take_profit=fresh_tp1,
                    volume=fresh_volume,
                )
            )

            final_execution_price = (
                self._decimal(
                    final_validation.execution_price,
                    "final execution price",
                )
                if final_validation.execution_price
                is not None
                else current_execution_price
            )

            final_broker_symbol = (
                final_validation.broker_symbol
                or broker_symbol
            )

            if not final_validation.approved:
                final_deviation = None
                final_deviation_percent = None

                if final_execution_price is not None:
                    final_deviation, final_deviation_percent = (
                        self._calculate_deviation(
                            signal_price,
                            final_execution_price,
                        )
                    )

                return TradeRevalidationResult(
                    approved=False,
                    status="final_broker_validation_failed",
                    intent_id=intent_id,
                    symbol=symbol,
                    direction=direction,
                    original_signal_entry_price=signal_price,
                    current_execution_price=final_execution_price,
                    entry_price=fresh_entry,
                    entry_zone=fresh_zone,
                    stop_loss=fresh_sl,
                    take_profit_1=fresh_tp1,
                    take_profit_2=fresh_tp2,
                    volume=fresh_volume,
                    risk_percent=requested_risk,
                    risk_reward_1=fresh_rr1,
                    risk_reward_2=fresh_rr2,
                    broker_symbol=final_broker_symbol,
                    setup_quality=fresh_quality,
                    market_bias=setup_bias or None,
                    signal_price_deviation=final_deviation,
                    signal_price_deviation_percent=(
                        final_deviation_percent
                    ),
                    checks=(
                        checks
                        + final_validation.checks
                    ),
                    warnings=(
                        warnings
                        + final_validation.warnings
                    ),
                    errors=final_validation.errors,
                    reasons=reasons,
                    message=(
                        "Fresh setup and position size were generated, "
                        "but final broker validation failed."
                    ),
                )

            checks.extend(
                final_validation.checks
            )

            warnings.extend(
                final_validation.warnings
            )

            # =========================================================
            # 13. Recalculate deviation one final time
            # =========================================================

            if final_execution_price is None:
                raise TradeRevalidationError(
                    "Final broker validation did not return "
                    "a current execution price."
                )

            signal_deviation, signal_deviation_percent = (
                self._calculate_deviation(
                    signal_price,
                    final_execution_price,
                )
            )

            # =========================================================
            # 14. Final trade geometry
            # =========================================================

            geometry_errors: list[str] = []

            if direction == "buy":

                if fresh_sl >= final_execution_price:
                    geometry_errors.append(
                        "Fresh BUY stop loss is not below "
                        "current execution price."
                    )

                if fresh_tp1 <= final_execution_price:
                    geometry_errors.append(
                        "Fresh BUY take profit 1 is not above "
                        "current execution price."
                    )

                if fresh_tp2 <= fresh_tp1:
                    geometry_errors.append(
                        "Fresh BUY take profit 2 must be above "
                        "take profit 1."
                    )

            else:

                if fresh_sl <= final_execution_price:
                    geometry_errors.append(
                        "Fresh SELL stop loss is not above "
                        "current execution price."
                    )

                if fresh_tp1 >= final_execution_price:
                    geometry_errors.append(
                        "Fresh SELL take profit 1 is not below "
                        "current execution price."
                    )

                if fresh_tp2 >= fresh_tp1:
                    geometry_errors.append(
                        "Fresh SELL take profit 2 must be below "
                        "take profit 1."
                    )

            if geometry_errors:
                return TradeRevalidationResult(
                    approved=False,
                    status="geometry_failed",
                    intent_id=intent_id,
                    symbol=symbol,
                    direction=direction,
                    original_signal_entry_price=signal_price,
                    current_execution_price=final_execution_price,
                    entry_price=fresh_entry,
                    entry_zone=fresh_zone,
                    stop_loss=fresh_sl,
                    take_profit_1=fresh_tp1,
                    take_profit_2=fresh_tp2,
                    volume=fresh_volume,
                    risk_percent=requested_risk,
                    risk_reward_1=fresh_rr1,
                    risk_reward_2=fresh_rr2,
                    broker_symbol=final_broker_symbol,
                    setup_quality=fresh_quality,
                    market_bias=setup_bias or None,
                    signal_price_deviation=signal_deviation,
                    signal_price_deviation_percent=(
                        signal_deviation_percent
                    ),
                    checks=checks,
                    warnings=warnings,
                    errors=geometry_errors,
                    reasons=reasons,
                    message=(
                        "Fresh setup failed final price geometry "
                        "validation."
                    ),
                )

            checks.append(
                "Fresh SL/TP geometry is valid against "
                "current execution price"
            )

            # =========================================================
            # 15. Reject poor-quality setup
            # =========================================================

            if (
                str(fresh_quality).strip().lower()
                == "poor"
            ):
                return TradeRevalidationResult(
                    approved=False,
                    status="poor_setup",
                    intent_id=intent_id,
                    symbol=symbol,
                    direction=direction,
                    original_signal_entry_price=signal_price,
                    current_execution_price=final_execution_price,
                    entry_price=fresh_entry,
                    entry_zone=fresh_zone,
                    stop_loss=fresh_sl,
                    take_profit_1=fresh_tp1,
                    take_profit_2=fresh_tp2,
                    volume=fresh_volume,
                    risk_percent=requested_risk,
                    risk_reward_1=fresh_rr1,
                    risk_reward_2=fresh_rr2,
                    broker_symbol=final_broker_symbol,
                    setup_quality=fresh_quality,
                    market_bias=setup_bias or None,
                    signal_price_deviation=signal_deviation,
                    signal_price_deviation_percent=(
                        signal_deviation_percent
                    ),
                    checks=checks,
                    warnings=warnings,
                    errors=[
                        "Fresh trade setup quality is poor."
                    ],
                    reasons=reasons,
                    message=(
                        "Trade rejected because the fresh setup "
                        "quality is poor."
                    ),
                )

            # =========================================================
            # 16. Final stale-signal handling
            # =========================================================

            if (
                signal_deviation_percent
                > self.MAX_SIGNAL_DEVIATION_PERCENT
            ):
                warnings.append(
                    "The original signal is stale, but the fresh "
                    "structural setup remains valid. This setup must "
                    "be treated as a new trade setup."
                )

                reasons.append(
                    "Fresh market structure replaced the stale "
                    "original setup."
                )

            else:
                reasons.append(
                    "Original signal remains within the permitted "
                    "execution deviation."
                )

            checks.append(
                "Fresh setup remains structurally valid after "
                "complete revalidation"
            )

            # =========================================================
            # 17. Successful result
            # =========================================================

            return TradeRevalidationResult(
                approved=True,
                status="revalidated",
                intent_id=intent_id,
                symbol=symbol,
                direction=direction,
                original_signal_entry_price=signal_price,
                current_execution_price=final_execution_price,
                entry_price=fresh_entry,
                entry_zone=fresh_zone,
                stop_loss=fresh_sl,
                take_profit_1=fresh_tp1,
                take_profit_2=fresh_tp2,
                volume=fresh_volume,
                risk_percent=requested_risk,
                risk_reward_1=fresh_rr1,
                risk_reward_2=fresh_rr2,
                broker_symbol=final_broker_symbol,
                setup_quality=fresh_quality,
                market_bias=setup_bias or None,
                signal_price_deviation=signal_deviation,
                signal_price_deviation_percent=(
                    signal_deviation_percent
                ),
                checks=checks,
                warnings=warnings,
                errors=[],
                reasons=reasons,
                message=(
                    "Trade revalidation passed. A fresh structural "
                    "setup, broker-compatible price normalization, "
                    "fresh position sizing and final broker validation "
                    "all passed. No MT5 order was sent."
                ),
            )

        except (
            TradeRevalidationError,
            MT5TradeSetupError,
            BrokerValidationError,
        ) as exc:

            return TradeRevalidationResult(
                approved=False,
                status="revalidation_error",
                intent_id=intent_id,
                symbol=symbol,
                direction=direction,
                original_signal_entry_price=(
                    signal_price
                    if signal_price is not None
                    else None
                ),
                current_execution_price=None,
                entry_price=None,
                risk_percent=(
                    requested_risk
                    if requested_risk is not None
                    else None
                ),
                checks=checks,
                warnings=warnings,
                errors=[str(exc)],
                reasons=reasons,
                message=(
                    "Trade revalidation could not be completed safely."
                ),
            )

        except Exception as exc:

            return TradeRevalidationResult(
                approved=False,
                status="revalidation_error",
                intent_id=intent_id,
                symbol=symbol,
                direction=direction,
                original_signal_entry_price=(
                    signal_price
                    if signal_price is not None
                    else None
                ),
                current_execution_price=None,
                entry_price=None,
                risk_percent=(
                    requested_risk
                    if requested_risk is not None
                    else None
                ),
                checks=checks,
                warnings=warnings,
                errors=[
                    f"Unexpected revalidation error: {exc}"
                ],
                reasons=reasons,
                message=(
                    "Trade revalidation failed safely. "
                    "No MT5 order was sent."
                ),
            )


trade_revalidation_service = TradeRevalidationService()