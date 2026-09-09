from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Dict, Optional

import MetaTrader5 as mt5

from app.mt5.connection import mt5_connection


class PositionSizeError(Exception):
    """Raised when position size cannot be calculated safely."""


class PositionSizeService:
    """
    Calculates broker-valid MT5 position volume from:

        Account equity/balance
        Risk percentage
        Entry price
        Stop-loss price
        MT5 tick size
        MT5 tick value
        Broker volume constraints

    The service does NOT send orders.

    It only calculates and validates the position size that the
    execution layer may use later.

    Application symbols and broker symbols are handled separately.

    Example:

        Application symbol:
            BTCUSD

        Broker symbol:
            BTCUSDm
    """

    DEFAULT_RISK_PERCENT = Decimal("1.00")

    MAX_RISK_PERCENT = Decimal("2.00")

    MIN_RISK_AMOUNT = Decimal("0.01")

    # Safety allowance for broker volume rounding.
    MAX_RISK_OVERRUN_PERCENT = Decimal("0.01")

    # =====================================
    # DECIMAL HELPERS
    # =====================================

    @staticmethod
    def _decimal(
        value: Any
    ) -> Optional[Decimal]:

        if value is None:
            return None

        try:

            return Decimal(
                str(value)
            )

        except (
            InvalidOperation,
            ValueError,
            TypeError,
        ):

            return None

    # =====================================
    # MT5 CONNECTION
    # =====================================

    def ensure_mt5_connection(
        self
    ) -> bool:

        try:

            if mt5_connection.is_connected():

                terminal = mt5.terminal_info()

                if terminal is not None:
                    return True

            connected = (
                mt5_connection.connect()
            )

            if not connected:
                return False

            terminal = mt5.terminal_info()

            return terminal is not None

        except Exception:

            return False

    # =====================================
    # SYMBOL RESOLUTION
    # =====================================

    def resolve_symbol(
        self,
        symbol: str
    ) -> str:
        """
        Resolve an application symbol to the actual broker symbol.

        Examples:

            BTCUSD  -> BTCUSDm
            XAUUSD  -> XAUUSDm
            EURUSD  -> EURUSDm
            GBPUSD  -> GBPUSDm

        The service first attempts an exact match.

        If the exact symbol does not exist, it searches the broker's
        available symbols for a matching broker suffix.
        """

        if not symbol:

            raise PositionSizeError(
                "Symbol is required"
            )

        requested = (
            str(symbol)
            .strip()
            .upper()
        )

        # =====================================
        # EXACT SYMBOL
        # =====================================

        try:

            info = mt5.symbol_info(
                requested
            )

            if info is not None:

                if not getattr(
                    info,
                    "visible",
                    True
                ):

                    selected = (
                        mt5.symbol_select(
                            requested,
                            True
                        )
                    )

                    if selected:

                        info = mt5.symbol_info(
                            requested
                        )

                if info is not None:

                    return requested

        except Exception:
            pass

        # =====================================
        # BROKER SYMBOL DISCOVERY
        # =====================================

        try:

            symbols = mt5.symbols_get()

        except Exception as exc:

            raise PositionSizeError(
                "Unable to retrieve symbols from MT5 broker"
            ) from exc

        if symbols is None:

            raise PositionSizeError(
                "MT5 broker returned no symbols"
            )

        requested_lower = (
            requested.lower()
        )

        matches = []

        # =====================================
        # DIRECT PREFIX MATCH
        # =====================================

        for item in symbols:

            name = str(
                getattr(
                    item,
                    "name",
                    ""
                )
            ).strip()

            if not name:
                continue

            name_lower = name.lower()

            # Exact match.
            if name_lower == requested_lower:

                matches.append(
                    name
                )

                continue

            # Common broker suffixes:
            #
            # BTCUSDm
            # BTCUSD.a
            # BTCUSD+
            # BTCUSD#
            # BTCUSDpro
            #
            if name_lower.startswith(
                requested_lower
            ):

                matches.append(
                    name
                )

        if matches:

            # Prefer the shortest matching symbol.
            matches.sort(
                key=lambda value: (
                    len(value),
                    value.lower(),
                )
            )

            resolved = matches[0]

            try:

                mt5.symbol_select(
                    resolved,
                    True
                )

            except Exception:
                pass

            return resolved

        # =====================================
        # NORMALIZED MATCH
        # =====================================

        normalized_requested = (
            requested
            .replace("/", "")
            .replace("_", "")
            .replace("-", "")
            .lower()
        )

        normalized_matches = []

        for item in symbols:

            name = str(
                getattr(
                    item,
                    "name",
                    ""
                )
            ).strip()

            if not name:
                continue

            normalized_name = (
                name
                .replace("/", "")
                .replace("_", "")
                .replace("-", "")
                .lower()
            )

            if normalized_name.startswith(
                normalized_requested
            ):

                normalized_matches.append(
                    name
                )

        if normalized_matches:

            normalized_matches.sort(
                key=lambda value: (
                    len(value),
                    value.lower(),
                )
            )

            resolved = (
                normalized_matches[0]
            )

            try:

                mt5.symbol_select(
                    resolved,
                    True
                )

            except Exception:
                pass

            return resolved

        raise PositionSizeError(
            f"Symbol {requested} is unavailable from the connected MT5 broker"
        )

    # =====================================
    # SYMBOL INFORMATION
    # =====================================

    def get_symbol_info(
        self,
        symbol: str
    ):
        """
        Resolve the application symbol and return:

            broker_symbol, symbol_info
        """

        broker_symbol = (
            self.resolve_symbol(
                symbol
            )
        )

        try:

            info = mt5.symbol_info(
                broker_symbol
            )

        except Exception as exc:

            raise PositionSizeError(
                f"Unable to retrieve MT5 symbol information "
                f"for {broker_symbol}"
            ) from exc

        if info is None:

            raise PositionSizeError(
                f"MT5 symbol information unavailable "
                f"for {broker_symbol}"
            )

        if not getattr(
            info,
            "visible",
            True
        ):

            selected = (
                mt5.symbol_select(
                    broker_symbol,
                    True
                )
            )

            if not selected:

                raise PositionSizeError(
                    f"Unable to select MT5 symbol "
                    f"{broker_symbol}"
                )

            info = mt5.symbol_info(
                broker_symbol
            )

            if info is None:

                raise PositionSizeError(
                    f"MT5 symbol information unavailable "
                    f"after selection for {broker_symbol}"
                )

        return (
            broker_symbol,
            info,
        )

    # =====================================
    # VOLUME DECIMAL PLACES
    # =====================================

    @staticmethod
    def _volume_precision(
        volume_step: Decimal,
    ) -> int:
        """
        Determine the number of decimal places required by the
        broker's volume step.

        Examples:

            1       -> 0
            0.1     -> 1
            0.01    -> 2
            0.001   -> 3
        """

        normalized = (
            volume_step.normalize()
        )

        exponent = (
            normalized
            .as_tuple()
            .exponent
        )

        if exponent >= 0:

            return 0

        return abs(exponent)

    # =====================================
    # ROUND VOLUME DOWN
    # =====================================

    def _round_volume_down(
        self,
        volume: Decimal,
        volume_step: Decimal,
    ) -> Decimal:

        if volume_step <= 0:

            raise PositionSizeError(
                "Invalid broker volume step"
            )

        steps = (
            volume
            / volume_step
        ).to_integral_value(
            rounding=ROUND_DOWN
        )

        rounded = (
            steps
            * volume_step
        )

        precision = (
            self._volume_precision(
                volume_step
            )
        )

        quantum = (
            Decimal("1")
            .scaleb(
                -precision
            )
        )

        return rounded.quantize(
            quantum,
            rounding=ROUND_DOWN,
        )

    # =====================================
    # TICK INFORMATION
    # =====================================

    def _get_tick_size(
        self,
        symbol_info,
    ) -> Decimal:

        tick_size = self._decimal(
            getattr(
                symbol_info,
                "trade_tick_size",
                None,
            )
        )

        if (
            tick_size is None
            or tick_size <= 0
        ):

            tick_size = self._decimal(
                getattr(
                    symbol_info,
                    "tick_size",
                    None,
                )
            )

        if (
            tick_size is None
            or tick_size <= 0
        ):

            raise PositionSizeError(
                "Broker tick size unavailable"
            )

        return tick_size

    # =====================================
    # TICK VALUE
    # =====================================

    def _get_tick_value(
        self,
        symbol_info,
        direction: str,
    ) -> Decimal:
        """
        Retrieve the appropriate MT5 tick value.

        Uses side-specific tick values when available and falls
        back to the general trade_tick_value.
        """

        if direction == "buy":

            value = self._decimal(
                getattr(
                    symbol_info,
                    "trade_tick_value_profit",
                    None,
                )
            )

        else:

            value = self._decimal(
                getattr(
                    symbol_info,
                    "trade_tick_value_loss",
                    None,
                )
            )

        if (
            value is None
            or value <= 0
        ):

            value = self._decimal(
                getattr(
                    symbol_info,
                    "trade_tick_value",
                    None,
                )
            )

        if (
            value is None
            or value <= 0
        ):

            raise PositionSizeError(
                "Broker tick value unavailable"
            )

        return value

    # =====================================
    # BROKER VOLUME RULES
    # =====================================

    def _get_volume_constraints(
        self,
        symbol_info,
    ):

        volume_min = self._decimal(
            getattr(
                symbol_info,
                "volume_min",
                None,
            )
        )

        volume_max = self._decimal(
            getattr(
                symbol_info,
                "volume_max",
                None,
            )
        )

        volume_step = self._decimal(
            getattr(
                symbol_info,
                "volume_step",
                None,
            )
        )

        if (
            volume_min is None
            or volume_min <= 0
        ):

            raise PositionSizeError(
                "Broker minimum volume unavailable"
            )

        if (
            volume_max is None
            or volume_max <= 0
        ):

            raise PositionSizeError(
                "Broker maximum volume unavailable"
            )

        if (
            volume_step is None
            or volume_step <= 0
        ):

            raise PositionSizeError(
                "Broker volume step unavailable"
            )

        return (
            volume_min,
            volume_max,
            volume_step,
        )

    # =====================================
    # RISK AMOUNT
    # =====================================

    def calculate_risk_amount(
        self,
        account_equity: Decimal,
        risk_percent: Decimal,
    ) -> Decimal:

        if account_equity <= 0:

            raise PositionSizeError(
                "Account equity must be greater than zero"
            )

        if risk_percent <= 0:

            raise PositionSizeError(
                "Risk percentage must be greater than zero"
            )

        if risk_percent > self.MAX_RISK_PERCENT:

            raise PositionSizeError(
                f"Risk percentage exceeds maximum "
                f"allowed {self.MAX_RISK_PERCENT}%"
            )

        risk_amount = (
            account_equity
            * risk_percent
            / Decimal("100")
        )

        if (
            risk_amount
            < self.MIN_RISK_AMOUNT
        ):

            raise PositionSizeError(
                "Calculated risk amount is too small"
            )

        return risk_amount

    # =====================================
    # LOSS PER LOT
    # =====================================

    def calculate_loss_per_lot(
        self,
        entry: Decimal,
        stop_loss: Decimal,
        tick_size: Decimal,
        tick_value: Decimal,
    ) -> Decimal:

        stop_distance = abs(
            entry
            - stop_loss
        )

        if stop_distance <= 0:

            raise PositionSizeError(
                "Entry and stop-loss cannot be equal"
            )

        ticks = (
            stop_distance
            / tick_size
        )

        loss_per_lot = (
            ticks
            * tick_value
        )

        if loss_per_lot <= 0:

            raise PositionSizeError(
                "Unable to calculate loss per lot"
            )

        return loss_per_lot

    # =====================================
    # CALCULATE RAW VOLUME
    # =====================================

    def calculate_raw_volume(
        self,
        risk_amount: Decimal,
        loss_per_lot: Decimal,
    ) -> Decimal:

        if risk_amount <= 0:

            raise PositionSizeError(
                "Risk amount must be greater than zero"
            )

        if loss_per_lot <= 0:

            raise PositionSizeError(
                "Loss per lot must be greater than zero"
            )

        return (
            risk_amount
            / loss_per_lot
        )

    # =====================================
    # BROKER-VALID VOLUME
    # =====================================

    def normalize_volume(
        self,
        raw_volume: Decimal,
        volume_min: Decimal,
        volume_max: Decimal,
        volume_step: Decimal,
    ) -> Decimal:

        if raw_volume <= 0:

            raise PositionSizeError(
                "Calculated volume is zero or negative"
            )

        rounded = (
            self._round_volume_down(
                raw_volume,
                volume_step,
            )
        )

        if rounded < volume_min:

            return Decimal("0")

        if rounded > volume_max:

            rounded = (
                self._round_volume_down(
                    volume_max,
                    volume_step,
                )
            )

        return rounded

    # =====================================
    # ACTUAL RISK
    # =====================================

    def calculate_actual_risk(
        self,
        volume: Decimal,
        loss_per_lot: Decimal,
    ) -> Decimal:

        return (
            volume
            * loss_per_lot
        )

    # =====================================
    # ACTUAL RISK PERCENTAGE
    # =====================================

    def calculate_actual_risk_percent(
        self,
        actual_risk: Decimal,
        account_equity: Decimal,
    ) -> Decimal:

        if account_equity <= 0:

            return Decimal("0")

        return (
            actual_risk
            / account_equity
            * Decimal("100")
        )

    # =====================================
    # MAIN CALCULATION
    # =====================================

    def calculate(
        self,
        symbol: str,
        direction: str,
        entry_price: Any,
        stop_loss: Any,
        risk_percent: Any = None,
        account_equity: Any = None,
    ) -> Dict[str, Any]:

        # =====================================
        # NORMALIZE SYMBOL
        # =====================================

        application_symbol = str(
            symbol or ""
        ).strip().upper()

        if not application_symbol:

            raise PositionSizeError(
                "Symbol is required"
            )

        # =====================================
        # NORMALIZE DIRECTION
        # =====================================

        direction = str(
            direction or ""
        ).strip().lower()

        if direction in {
            "long",
            "buy",
        }:

            direction = "buy"

        elif direction in {
            "short",
            "sell",
        }:

            direction = "sell"

        else:

            raise PositionSizeError(
                "Invalid direction; expected buy/long or sell/short"
            )

        # =====================================
        # PRICE INPUTS
        # =====================================

        entry = self._decimal(
            entry_price
        )

        stop = self._decimal(
            stop_loss
        )

        if entry is None:

            raise PositionSizeError(
                "Invalid entry price"
            )

        if stop is None:

            raise PositionSizeError(
                "Invalid stop-loss price"
            )

        if entry <= 0:

            raise PositionSizeError(
                "Entry price must be greater than zero"
            )

        if stop <= 0:

            raise PositionSizeError(
                "Stop-loss price must be greater than zero"
            )

        # =====================================
        # DIRECTION GEOMETRY
        # =====================================

        if direction == "buy":

            if stop >= entry:

                raise PositionSizeError(
                    "BUY stop loss must be below entry"
                )

        else:

            if stop <= entry:

                raise PositionSizeError(
                    "SELL stop loss must be above entry"
                )

        # =====================================
        # RISK %
        # =====================================

        risk = self._decimal(
            risk_percent
        )

        if risk is None:

            risk = (
                self.DEFAULT_RISK_PERCENT
            )

        # =====================================
        # MT5 CONNECTION
        # =====================================

        if not self.ensure_mt5_connection():

            raise PositionSizeError(
                "MT5 connection failed"
            )

        # =====================================
        # ACCOUNT
        # =====================================

        account = mt5.account_info()

        if account is None:

            raise PositionSizeError(
                "MT5 account unavailable"
            )

        if account_equity is None:

            account_equity_decimal = (
                self._decimal(
                    getattr(
                        account,
                        "equity",
                        None,
                    )
                )
            )

        else:

            account_equity_decimal = (
                self._decimal(
                    account_equity
                )
            )

        if (
            account_equity_decimal is None
            or account_equity_decimal <= 0
        ):

            raise PositionSizeError(
                "Invalid account equity"
            )

        # =====================================
        # ACCOUNT RISK
        # =====================================

        risk_amount = (
            self.calculate_risk_amount(
                account_equity_decimal,
                risk,
            )
        )

        # =====================================
        # BROKER SYMBOL
        # =====================================

        (
            broker_symbol,
            symbol_info,
        ) = self.get_symbol_info(
            application_symbol
        )

        # =====================================
        # BROKER DATA
        # =====================================

        tick_size = (
            self._get_tick_size(
                symbol_info
            )
        )

        tick_value = (
            self._get_tick_value(
                symbol_info,
                direction,
            )
        )

        (
            volume_min,
            volume_max,
            volume_step,
        ) = self._get_volume_constraints(
            symbol_info
        )

        # =====================================
        # STOP DISTANCE
        # =====================================

        stop_distance = abs(
            entry
            - stop
        )

        point = self._decimal(
            getattr(
                symbol_info,
                "point",
                None,
            )
        )

        stop_distance_points = None

        if (
            point is not None
            and point > 0
        ):

            stop_distance_points = (
                stop_distance
                / point
            )

        # =====================================
        # LOSS PER LOT
        # =====================================

        loss_per_lot = (
            self.calculate_loss_per_lot(
                entry,
                stop,
                tick_size,
                tick_value,
            )
        )

        # =====================================
        # RAW VOLUME
        # =====================================

        raw_volume = (
            self.calculate_raw_volume(
                risk_amount,
                loss_per_lot,
            )
        )

        # =====================================
        # BROKER VOLUME
        # =====================================

        volume = (
            self.normalize_volume(
                raw_volume,
                volume_min,
                volume_max,
                volume_step,
            )
        )

        # =====================================
        # MINIMUM LOT CHECK
        # =====================================

        if volume <= 0:

            return {
                "approved": False,

                "status":
                    "volume_below_minimum",

                "symbol":
                    application_symbol,

                "broker_symbol":
                    broker_symbol,

                "direction":
                    direction,

                "entry_price":
                    float(entry),

                "stop_loss":
                    float(stop),

                "stop_distance":
                    float(stop_distance),

                "stop_distance_points":
                    (
                        float(
                            stop_distance_points
                        )
                        if stop_distance_points
                        is not None
                        else None
                    ),

                "risk_percent":
                    float(risk),

                "risk_amount":
                    float(risk_amount),

                "loss_per_lot":
                    float(loss_per_lot),

                "raw_volume":
                    float(raw_volume),

                "volume":
                    0.0,

                "volume_min":
                    float(volume_min),

                "volume_max":
                    float(volume_max),

                "volume_step":
                    float(volume_step),

                "account_equity":
                    float(
                        account_equity_decimal
                    ),

                "message":
                    "Calculated position size is below the broker minimum volume",
            }

        # =====================================
        # ACTUAL RISK
        # =====================================

        actual_risk = (
            self.calculate_actual_risk(
                volume,
                loss_per_lot,
            )
        )

        actual_risk_percent = (
            self.calculate_actual_risk_percent(
                actual_risk,
                account_equity_decimal,
            )
        )

        # =====================================
        # RISK OVERRUN CHECK
        # =====================================

        maximum_allowed_risk = (
            risk
            + self.MAX_RISK_OVERRUN_PERCENT
        )

        if (
            actual_risk_percent
            > maximum_allowed_risk
        ):

            return {
                "approved": False,

                "status":
                    "risk_limit_exceeded",

                "symbol":
                    application_symbol,

                "broker_symbol":
                    broker_symbol,

                "direction":
                    direction,

                "entry_price":
                    float(entry),

                "stop_loss":
                    float(stop),

                "stop_distance":
                    float(stop_distance),

                "stop_distance_points":
                    (
                        float(
                            stop_distance_points
                        )
                        if stop_distance_points
                        is not None
                        else None
                    ),

                "risk_percent":
                    float(risk),

                "risk_amount":
                    float(risk_amount),

                "actual_risk":
                    float(actual_risk),

                "actual_risk_percent":
                    float(actual_risk_percent),

                "loss_per_lot":
                    float(loss_per_lot),

                "raw_volume":
                    float(raw_volume),

                "volume":
                    float(volume),

                "volume_min":
                    float(volume_min),

                "volume_max":
                    float(volume_max),

                "volume_step":
                    float(volume_step),

                "account_equity":
                    float(
                        account_equity_decimal
                    ),

                "message":
                    "Broker-normalized volume exceeds the permitted risk limit",
            }

        # =====================================
        # FINAL RESULT
        # =====================================

        return {
            "approved": True,

            "status":
                "calculated",

            # Application symbol.
            "symbol":
                application_symbol,

            # Actual MT5 broker symbol.
            "broker_symbol":
                broker_symbol,

            "direction":
                direction,

            "entry_price":
                float(entry),

            "stop_loss":
                float(stop),

            "stop_distance":
                float(stop_distance),

            "stop_distance_points":
                (
                    float(
                        stop_distance_points
                    )
                    if stop_distance_points
                    is not None
                    else None
                ),

            "risk_percent":
                float(risk),

            "risk_amount":
                float(risk_amount),

            "actual_risk":
                float(actual_risk),

            "actual_risk_percent":
                float(actual_risk_percent),

            "tick_size":
                float(tick_size),

            "tick_value":
                float(tick_value),

            "loss_per_lot":
                float(loss_per_lot),

            "raw_volume":
                float(raw_volume),

            "volume":
                float(volume),

            "volume_min":
                float(volume_min),

            "volume_max":
                float(volume_max),

            "volume_step":
                float(volume_step),

            "account_equity":
                float(
                    account_equity_decimal
                ),

            "message":
                "Position size calculated successfully",
        }


# =====================================
# SINGLETON
# =====================================

position_size_service = (
    PositionSizeService()
)