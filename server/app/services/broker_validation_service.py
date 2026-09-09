from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import MetaTrader5 as mt5

from app.mt5.connection import mt5_connection


class BrokerValidationError(Exception):
    """Raised when broker validation cannot be completed."""


@dataclass
class BrokerValidationResult:
    approved: bool
    status: str
    symbol: str
    broker_symbol: Optional[str]
    direction: str
    entry_price: Optional[float]
    execution_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    volume: Optional[float]

    bid: Optional[float]
    ask: Optional[float]
    spread: Optional[float]
    spread_points: Optional[float]

    digits: Optional[int]
    point: Optional[float]

    volume_min: Optional[float]
    volume_max: Optional[float]
    volume_step: Optional[float]

    tick_size: Optional[float]
    tick_value: Optional[float]

    trade_stops_level: Optional[int]
    trade_freeze_level: Optional[int]

    minimum_stop_distance: Optional[float]
    minimum_stop_distance_points: Optional[float]

    margin_required: Optional[float]
    free_margin: Optional[float]

    filling_mode: Optional[int]
    trade_mode: Optional[int]

    checks: list[str]
    warnings: list[str]
    errors: list[str]

    message: str

    def serialize(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "status": self.status,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "execution_price": self.execution_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "volume": self.volume,
            "market": {
                "bid": self.bid,
                "ask": self.ask,
                "spread": self.spread,
                "spread_points": self.spread_points,
            },
            "symbol_specification": {
                "digits": self.digits,
                "point": self.point,
                "volume_min": self.volume_min,
                "volume_max": self.volume_max,
                "volume_step": self.volume_step,
                "tick_size": self.tick_size,
                "tick_value": self.tick_value,
                "trade_stops_level": self.trade_stops_level,
                "trade_freeze_level": self.trade_freeze_level,
                "filling_mode": self.filling_mode,
                "trade_mode": self.trade_mode,
            },
            "minimum_stop_distance": self.minimum_stop_distance,
            "minimum_stop_distance_points": self.minimum_stop_distance_points,
            "margin_required": self.margin_required,
            "free_margin": self.free_margin,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "message": self.message,
        }


class BrokerValidationService:
    """
    Validates a proposed MT5 trade against the live broker.

    IMPORTANT:
    This service DOES NOT send orders.

    It only determines whether the proposed trade is
    currently acceptable for broker execution.
    """

    SUPPORTED_DIRECTIONS = {
        "buy": mt5.ORDER_TYPE_BUY,
        "sell": mt5.ORDER_TYPE_SELL,
        "long": mt5.ORDER_TYPE_BUY,
        "short": mt5.ORDER_TYPE_SELL,
    }

    def __init__(self):
        self.connection = mt5_connection

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise BrokerValidationError(
                f"Invalid numeric value: {value}"
            ) from exc

    @staticmethod
    def _float(value: Any) -> Optional[float]:
        if value is None:
            return None

        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _normalize_direction(direction: str) -> str:
        value = str(direction).strip().lower()

        if value in {"buy", "long"}:
            return "buy"

        if value in {"sell", "short"}:
            return "sell"

        raise BrokerValidationError(
            "Direction must be buy, sell, long, or short"
        )

    # ============================================================
    # SYMBOL RESOLUTION
    # ============================================================

    def resolve_symbol(self, symbol: str) -> str:
        requested = str(symbol).strip()

        if not requested:
            raise BrokerValidationError(
                "Trading symbol is required"
            )

        # Exact broker symbol
        info = mt5.symbol_info(requested)

        if info is not None:
            if not info.visible:
                mt5.symbol_select(requested, True)

            return requested

        # Search broker symbols
        symbols = mt5.symbols_get()

        if symbols is None:
            error = mt5.last_error()

            raise BrokerValidationError(
                f"Unable to retrieve broker symbols: {error}"
            )

        requested_lower = requested.lower()

        # Direct case-insensitive match
        for item in symbols:
            name = getattr(item, "name", "")

            if name.lower() == requested_lower:
                if not item.visible:
                    mt5.symbol_select(name, True)

                return name

        # Common broker suffixes:
        # BTCUSD -> BTCUSDm
        # EURUSD -> EURUSD.a
        # XAUUSD -> XAUUSDm
        suffix_matches = []

        for item in symbols:
            name = getattr(item, "name", "")
            name_lower = name.lower()

            if name_lower.startswith(requested_lower):
                suffix_matches.append(name)

        if suffix_matches:
            # Prefer short suffixes such as "m"
            suffix_matches.sort(
                key=lambda name: (
                    len(name),
                    name.lower(),
                )
            )

            resolved = suffix_matches[0]

            if not mt5.symbol_select(resolved, True):
                raise BrokerValidationError(
                    f"Broker symbol found but could not be selected: {resolved}"
                )

            return resolved

        raise BrokerValidationError(
            f"Broker symbol unavailable: {requested}"
        )

    # ============================================================
    # VALIDATE VOLUME
    # ============================================================

    def _validate_volume(
        self,
        volume: Decimal,
        info: Any,
        checks: list[str],
        warnings: list[str],
        errors: list[str],
    ) -> None:

        minimum = self._decimal(info.volume_min)
        maximum = self._decimal(info.volume_max)
        step = self._decimal(info.volume_step)

        if volume <= Decimal("0"):
            errors.append(
                "Trade volume must be greater than zero"
            )
            return

        if volume < minimum:
            errors.append(
                f"Volume {volume} is below broker minimum {minimum}"
            )

        if volume > maximum:
            errors.append(
                f"Volume {volume} exceeds broker maximum {maximum}"
            )

        if step > Decimal("0"):
            relative = (
                (volume - minimum) / step
            )

            if relative != relative.to_integral_value():
                warnings.append(
                    f"Volume {volume} does not align exactly with "
                    f"broker volume step {step}"
                )

        if not errors:
            checks.append(
                "Volume satisfies broker limits"
            )

    # ============================================================
    # VALIDATE PRICE
    # ============================================================

    def _validate_price(
        self,
        price: Decimal,
        info: Any,
        field_name: str,
        checks: list[str],
        errors: list[str],
    ) -> None:

        digits = int(info.digits)

        rounded = price.quantize(
            Decimal("1").scaleb(-digits)
        )

        if price != rounded:
            errors.append(
                f"{field_name} {price} exceeds broker precision "
                f"of {digits} decimal places"
            )
            return

        checks.append(
            f"{field_name} precision is broker-compatible"
        )

    # ============================================================
    # VALIDATE MARKET SIDE
    # ============================================================

    def _validate_market_side(
        self,
        direction: str,
        execution_price: Decimal,
        bid: Decimal,
        ask: Decimal,
        checks: list[str],
        errors: list[str],
    ) -> None:

        if direction == "buy":

            if execution_price != ask:
                errors.append(
                    f"BUY execution price must use the live ask price "
                    f"{ask}"
                )
                return

        else:

            if execution_price != bid:
                errors.append(
                    f"SELL execution price must use the live bid price "
                    f"{bid}"
                )
                return

        checks.append(
            "Execution price matches the correct live market side"
        )

    # ============================================================
    # VALIDATE SL
    # ============================================================

    def _validate_stop_loss(
        self,
        direction: str,
        execution_price: Decimal,
        stop_loss: Optional[Decimal],
        minimum_distance: Decimal,
        checks: list[str],
        errors: list[str],
    ) -> None:

        if stop_loss is None:
            errors.append(
                "Stop loss is required before broker execution"
            )
            return

        if direction == "buy":

            if stop_loss >= execution_price:
                errors.append(
                    "BUY stop loss must be below execution price"
                )
                return

        else:

            if stop_loss <= execution_price:
                errors.append(
                    "SELL stop loss must be above execution price"
                )
                return

        distance = abs(
            execution_price - stop_loss
        )

        if distance < minimum_distance:
            errors.append(
                f"Stop loss distance {distance} is below broker "
                f"minimum {minimum_distance}"
            )
            return

        checks.append(
            "Stop loss geometry satisfies broker requirements"
        )

    # ============================================================
    # VALIDATE TAKE PROFIT
    # ============================================================

    def _validate_take_profit(
        self,
        direction: str,
        execution_price: Decimal,
        take_profit: Optional[Decimal],
        minimum_distance: Decimal,
        checks: list[str],
        warnings: list[str],
    ) -> None:

        if take_profit is None:
            warnings.append(
                "No take profit supplied for broker validation"
            )
            return

        if direction == "buy":

            if take_profit <= execution_price:
                warnings.append(
                    "BUY take profit is not above execution price"
                )
                return

        else:

            if take_profit >= execution_price:
                warnings.append(
                    "SELL take profit is not below execution price"
                )
                return

        distance = abs(
            execution_price - take_profit
        )

        if distance < minimum_distance:
            warnings.append(
                f"Take profit distance {distance} is below broker "
                f"minimum {minimum_distance}"
            )
            return

        checks.append(
            "Take profit geometry satisfies broker requirements"
        )

    # ============================================================
    # MAIN VALIDATION
    # ============================================================

    def validate(
        self,
        symbol: str,
        direction: str,
        entry_price: Any,
        stop_loss: Any,
        take_profit: Any = None,
        volume: Any = None,
    ) -> BrokerValidationResult:

        checks: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []

        normalized_direction = self._normalize_direction(
            direction
        )

        application_symbol = str(symbol).strip()

        if not application_symbol:
            raise BrokerValidationError(
                "Trading symbol is required"
            )

        # --------------------------------------------------------
        # MT5 INITIALIZATION
        # --------------------------------------------------------

        try:
            connected = self.connection.ensure_connected()
        except AttributeError:
            connected = self.connection.connect()

        if not connected:
            error = mt5.last_error()

            return BrokerValidationResult(
                approved=False,
                status="broker_unavailable",
                symbol=application_symbol,
                broker_symbol=None,
                direction=normalized_direction,
                entry_price=self._float(entry_price),
                execution_price=None,
                stop_loss=self._float(stop_loss),
                take_profit=self._float(take_profit),
                volume=self._float(volume),
                bid=None,
                ask=None,
                spread=None,
                spread_points=None,
                digits=None,
                point=None,
                volume_min=None,
                volume_max=None,
                volume_step=None,
                tick_size=None,
                tick_value=None,
                trade_stops_level=None,
                trade_freeze_level=None,
                minimum_stop_distance=None,
                minimum_stop_distance_points=None,
                margin_required=None,
                free_margin=None,
                filling_mode=None,
                trade_mode=None,
                checks=checks,
                warnings=warnings,
                errors=[
                    f"MT5 connection unavailable: {error}"
                ],
                message="Broker validation could not connect to MetaTrader 5",
            )

        # --------------------------------------------------------
        # SYMBOL
        # --------------------------------------------------------

        try:
            broker_symbol = self.resolve_symbol(
                application_symbol
            )
        except BrokerValidationError as exc:

            return BrokerValidationResult(
                approved=False,
                status="symbol_unavailable",
                symbol=application_symbol,
                broker_symbol=None,
                direction=normalized_direction,
                entry_price=self._float(entry_price),
                execution_price=None,
                stop_loss=self._float(stop_loss),
                take_profit=self._float(take_profit),
                volume=self._float(volume),
                bid=None,
                ask=None,
                spread=None,
                spread_points=None,
                digits=None,
                point=None,
                volume_min=None,
                volume_max=None,
                volume_step=None,
                tick_size=None,
                tick_value=None,
                trade_stops_level=None,
                trade_freeze_level=None,
                minimum_stop_distance=None,
                minimum_stop_distance_points=None,
                margin_required=None,
                free_margin=None,
                filling_mode=None,
                trade_mode=None,
                checks=checks,
                warnings=warnings,
                errors=[str(exc)],
                message="Broker symbol could not be resolved",
            )

        # --------------------------------------------------------
        # SYMBOL INFO
        # --------------------------------------------------------

        info = mt5.symbol_info(broker_symbol)

        if info is None:

            error = mt5.last_error()

            return BrokerValidationResult(
                approved=False,
                status="symbol_info_unavailable",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                entry_price=self._float(entry_price),
                execution_price=None,
                stop_loss=self._float(stop_loss),
                take_profit=self._float(take_profit),
                volume=self._float(volume),
                bid=None,
                ask=None,
                spread=None,
                spread_points=None,
                digits=None,
                point=None,
                volume_min=None,
                volume_max=None,
                volume_step=None,
                tick_size=None,
                tick_value=None,
                trade_stops_level=None,
                trade_freeze_level=None,
                minimum_stop_distance=None,
                minimum_stop_distance_points=None,
                margin_required=None,
                free_margin=None,
                filling_mode=None,
                trade_mode=None,
                checks=checks,
                warnings=warnings,
                errors=[
                    f"Unable to read broker symbol information: {error}"
                ],
                message="Broker symbol information unavailable",
            )

        checks.append(
            f"Broker symbol resolved: {application_symbol} -> {broker_symbol}"
        )

        # --------------------------------------------------------
        # SELECT SYMBOL
        # --------------------------------------------------------

        if not info.visible:

            if not mt5.symbol_select(
                broker_symbol,
                True,
            ):
                error = mt5.last_error()

                return BrokerValidationResult(
                    approved=False,
                    status="symbol_selection_failed",
                    symbol=application_symbol,
                    broker_symbol=broker_symbol,
                    direction=normalized_direction,
                    entry_price=self._float(entry_price),
                    execution_price=None,
                    stop_loss=self._float(stop_loss),
                    take_profit=self._float(take_profit),
                    volume=self._float(volume),
                    bid=None,
                    ask=None,
                    spread=None,
                    spread_points=None,
                    digits=int(info.digits),
                    point=self._float(info.point),
                    volume_min=self._float(info.volume_min),
                    volume_max=self._float(info.volume_max),
                    volume_step=self._float(info.volume_step),
                    tick_size=self._float(info.trade_tick_size),
                    tick_value=self._float(info.trade_tick_value),
                    trade_stops_level=int(info.trade_stops_level),
                    trade_freeze_level=int(info.trade_freeze_level),
                    minimum_stop_distance=None,
                    minimum_stop_distance_points=None,
                    margin_required=None,
                    free_margin=None,
                    filling_mode=int(info.filling_mode),
                    trade_mode=int(info.trade_mode),
                    checks=checks,
                    warnings=warnings,
                    errors=[
                        f"Unable to select broker symbol: {error}"
                    ],
                    message="Broker symbol could not be selected",
                )

        # --------------------------------------------------------
        # LIVE TICK
        # --------------------------------------------------------

        tick = mt5.symbol_info_tick(
            broker_symbol
        )

        if tick is None:

            error = mt5.last_error()

            return BrokerValidationResult(
                approved=False,
                status="tick_unavailable",
                symbol=application_symbol,
                broker_symbol=broker_symbol,
                direction=normalized_direction,
                entry_price=self._float(entry_price),
                execution_price=None,
                stop_loss=self._float(stop_loss),
                take_profit=self._float(take_profit),
                volume=self._float(volume),
                bid=None,
                ask=None,
                spread=None,
                spread_points=None,
                digits=int(info.digits),
                point=self._float(info.point),
                volume_min=self._float(info.volume_min),
                volume_max=self._float(info.volume_max),
                volume_step=self._float(info.volume_step),
                tick_size=self._float(info.trade_tick_size),
                tick_value=self._float(info.trade_tick_value),
                trade_stops_level=int(info.trade_stops_level),
                trade_freeze_level=int(info.trade_freeze_level),
                minimum_stop_distance=None,
                minimum_stop_distance_points=None,
                margin_required=None,
                free_margin=None,
                filling_mode=int(info.filling_mode),
                trade_mode=int(info.trade_mode),
                checks=checks,
                warnings=warnings,
                errors=[
                    f"Live tick unavailable: {error}"
                ],
                message="Live broker price unavailable",
            )

        bid = self._decimal(tick.bid)
        ask = self._decimal(tick.ask)
        point = self._decimal(info.point)

        if bid <= Decimal("0") or ask <= Decimal("0"):
            errors.append(
                "Broker returned an invalid bid/ask"
            )

        if ask < bid:
            errors.append(
                "Broker returned ask below bid"
            )

        spread = ask - bid

        spread_points = (
            spread / point
            if point > Decimal("0")
            else Decimal("0")
        )

        checks.append(
            "Live bid/ask received from broker"
        )

        # --------------------------------------------------------
        # EXECUTION PRICE
        # --------------------------------------------------------

        execution_price = (
            ask
            if normalized_direction == "buy"
            else bid
        )

        supplied_entry = (
            self._decimal(entry_price)
            if entry_price is not None
            else None
        )

        if supplied_entry is None:

            errors.append(
                "Entry price is required"
            )

        else:

            # We intentionally do not execute at an old signal price.
            # Market execution must use the current broker side.
            price_difference = abs(
                supplied_entry - execution_price
            )

            tolerance = point

            if price_difference > tolerance:
                warnings.append(
                    f"Signal entry {supplied_entry} differs from "
                    f"current executable price {execution_price} "
                    f"by {price_difference}"
                )

        # --------------------------------------------------------
        # TRADE MODE
        # --------------------------------------------------------

        trade_mode = int(info.trade_mode)

        if trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
            errors.append(
                "Broker has disabled trading for this symbol"
            )
        elif trade_mode == mt5.SYMBOL_TRADE_MODE_CLOSEONLY:
            errors.append(
                "Broker currently allows closing only for this symbol"
            )
        elif trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
            checks.append(
                "Broker symbol permits full trading"
            )
        else:
            warnings.append(
                f"Broker returned trade mode {trade_mode}"
            )

        # --------------------------------------------------------
        # VOLUME
        # --------------------------------------------------------

        requested_volume = (
            self._decimal(volume)
            if volume is not None
            else None
        )

        if requested_volume is None:

            errors.append(
                "Trade volume is required"
            )

        else:

            self._validate_volume(
                requested_volume,
                info,
                checks,
                warnings,
                errors,
            )

        # --------------------------------------------------------
        # PRICE PRECISION
        # --------------------------------------------------------

        if supplied_entry is not None:
            self._validate_price(
                execution_price,
                info,
                "Execution price",
                checks,
                errors,
            )

        supplied_stop = (
            self._decimal(stop_loss)
            if stop_loss is not None
            else None
        )

        supplied_tp = (
            self._decimal(take_profit)
            if take_profit is not None
            else None
        )

        if supplied_stop is not None:

            self._validate_price(
                supplied_stop,
                info,
                "Stop loss",
                checks,
                errors,
            )

        if supplied_tp is not None:

            self._validate_price(
                supplied_tp,
                info,
                "Take profit",
                checks,
                errors,
            )

        # --------------------------------------------------------
        # BROKER STOP DISTANCE
        # --------------------------------------------------------

        stops_level_points = int(
            getattr(
                info,
                "trade_stops_level",
                0,
            )
            or 0
        )

        freeze_level_points = int(
            getattr(
                info,
                "trade_freeze_level",
                0,
            )
            or 0
        )

        minimum_stop_distance = (
            Decimal(stops_level_points) * point
        )

        # Some brokers report zero stops level.
        # In that case there is no explicit minimum from this field.
        if stops_level_points > 0:

            checks.append(
                f"Broker minimum stop distance: "
                f"{stops_level_points} points"
            )

        else:

            warnings.append(
                "Broker reports zero minimum stop distance"
            )

        if freeze_level_points > 0:

            warnings.append(
                f"Broker freeze level is "
                f"{freeze_level_points} points"
            )

        # --------------------------------------------------------
        # SL / TP GEOMETRY
        # --------------------------------------------------------

        self._validate_stop_loss(
            normalized_direction,
            execution_price,
            supplied_stop,
            minimum_stop_distance,
            checks,
            errors,
        )

        self._validate_take_profit(
            normalized_direction,
            execution_price,
            supplied_tp,
            minimum_stop_distance,
            checks,
            warnings,
        )

        # --------------------------------------------------------
        # FILLING MODE
        # --------------------------------------------------------

        filling_mode = int(
            getattr(
                info,
                "filling_mode",
                0,
            )
        )

        if filling_mode >= 0:

            checks.append(
                f"Broker filling mode available: {filling_mode}"
            )

        # --------------------------------------------------------
        # MARGIN
        # --------------------------------------------------------

        margin_required = None
        free_margin = None

        if requested_volume is not None:

            order_type = self.SUPPORTED_DIRECTIONS[
                normalized_direction
            ]

            margin_required_raw = mt5.order_calc_margin(
                order_type,
                broker_symbol,
                float(requested_volume),
                float(execution_price),
            )

            if margin_required_raw is None:

                error = mt5.last_error()

                warnings.append(
                    f"Unable to calculate broker margin: {error}"
                )

            else:

                margin_required = Decimal(
                    str(margin_required_raw)
                )

                account_info = mt5.account_info()

                if account_info is not None:

                    free_margin = Decimal(
                        str(account_info.margin_free)
                    )

                    if margin_required > free_margin:

                        errors.append(
                            f"Required margin {margin_required} "
                            f"exceeds free margin {free_margin}"
                        )

                    else:

                        checks.append(
                            "Required margin is within available free margin"
                        )

        # --------------------------------------------------------
        # FINAL RESULT
        # --------------------------------------------------------

        approved = len(errors) == 0

        if approved:

            status = "approved"

            message = (
                "Broker validation passed. "
                "Trade is eligible for execution preview."
            )

        else:

            status = "rejected"

            message = (
                "Broker validation failed. "
                "Trade must not be sent to MT5."
            )

        return BrokerValidationResult(
            approved=approved,
            status=status,
            symbol=application_symbol,
            broker_symbol=broker_symbol,
            direction=normalized_direction,
            entry_price=self._float(supplied_entry),
            execution_price=self._float(execution_price),
            stop_loss=self._float(supplied_stop),
            take_profit=self._float(supplied_tp),
            volume=self._float(requested_volume),
            bid=self._float(bid),
            ask=self._float(ask),
            spread=self._float(spread),
            spread_points=self._float(spread_points),
            digits=int(info.digits),
            point=self._float(point),
            volume_min=self._float(info.volume_min),
            volume_max=self._float(info.volume_max),
            volume_step=self._float(info.volume_step),
            tick_size=self._float(
                getattr(info, "trade_tick_size", None)
            ),
            tick_value=self._float(
                getattr(info, "trade_tick_value", None)
            ),
            trade_stops_level=stops_level_points,
            trade_freeze_level=freeze_level_points,
            minimum_stop_distance=self._float(
                minimum_stop_distance
            ),
            minimum_stop_distance_points=float(
                stops_level_points
            ),
            margin_required=self._float(
                margin_required
            ),
            free_margin=self._float(
                free_margin
            ),
            filling_mode=filling_mode,
            trade_mode=trade_mode,
            checks=checks,
            warnings=warnings,
            errors=errors,
            message=message,
        )


broker_validation_service = BrokerValidationService()