from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

import MetaTrader5 as mt5

from app.mt5.connection import mt5_connection


class RiskGate:

    # =====================================
    # RISK SETTINGS
    # =====================================

    MIN_CONFIDENCE = Decimal("60")
    MIN_RISK_REWARD = Decimal("2.00")
    MAX_RISK_PERCENT = Decimal("2.00")
    DEFAULT_RISK_PERCENT = Decimal("1.00")

    MIN_FREE_MARGIN = Decimal("50")
    MAX_OPEN_TRADES = 5

    # Generic hard floor.
    # The broker/instrument spread is also inspected.
    MAX_SPREAD_POINTS = Decimal("5000")

    # Application-level minimum.
    MIN_STOP_DISTANCE_POINTS = Decimal("5")

    # =====================================
    # HELPERS
    # =====================================

    @staticmethod
    def _decimal(value: Any) -> Optional[Decimal]:
        if value is None:
            return None

        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _normalize_direction(direction: Any) -> str:
        value = str(direction or "").strip().lower()

        if value in {"buy", "long"}:
            return "buy"

        if value in {"sell", "short"}:
            return "sell"

        return ""

    @staticmethod
    def _normalize_quality(value: Any) -> str:
        return str(value or "poor").strip().lower()

    # =====================================
    # MT5 CONNECTION
    # =====================================

    def ensure_mt5_connection(self) -> bool:
        try:
            if mt5_connection.is_connected():
                terminal = mt5.terminal_info()

                if terminal is not None:
                    return True

            connected = mt5_connection.connect()

            if not connected:
                return False

            return mt5.terminal_info() is not None

        except Exception:
            return False

    # =====================================
    # ACCOUNT
    # =====================================

    def _get_account(self):
        try:
            return mt5.account_info()
        except Exception:
            return None

    # =====================================
    # POSITIONS
    # =====================================

    def _get_open_positions(self):
        try:
            positions = mt5.positions_get()

            if positions is None:
                return []

            return list(positions)

        except Exception:
            return []

    # =====================================
    # BROKER SYMBOL RESOLUTION
    # =====================================

    def _resolve_broker_symbol(
        self,
        application_symbol: str,
    ) -> Optional[str]:
        """
        Resolve application symbols such as:

            BTCUSD -> BTCUSDm
            XAUUSD -> XAUUSDm
            EURUSD -> EURUSDm

        while still accepting an already-resolved broker symbol.
        """

        if not application_symbol:
            return None

        requested = application_symbol.strip().upper()

        # ---------------------------------
        # Exact symbol
        # ---------------------------------

        try:
            info = mt5.symbol_info(requested)

            if info is not None:
                if not info.visible:
                    if not mt5.symbol_select(requested, True):
                        return None

                return requested

        except Exception:
            pass

        # ---------------------------------
        # Discover broker symbols
        # ---------------------------------

        try:
            symbols = mt5.symbols_get()

        except Exception:
            symbols = None

        if not symbols:
            return None

        requested_normalized = (
            requested
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
        )

        # Exact normalized match
        for item in symbols:

            name = str(
                getattr(item, "name", "")
            ).strip()

            if not name:
                continue

            normalized = (
                name.upper()
                .replace("/", "")
                .replace("-", "")
                .replace("_", "")
            )

            if normalized == requested_normalized:

                try:
                    if not item.visible:
                        if not mt5.symbol_select(name, True):
                            continue
                except Exception:
                    continue

                return name

        # ---------------------------------
        # Broker suffix match
        # ---------------------------------

        common_suffixes = (
            "M",
            ".A",
            "+",
            "#",
            ".PRO",
            "PRO",
        )

        for suffix in common_suffixes:

            candidate = f"{requested}{suffix}"

            for item in symbols:

                name = str(
                    getattr(item, "name", "")
                ).strip()

                if name.upper() != candidate:
                    continue

                try:
                    if not item.visible:
                        if not mt5.symbol_select(name, True):
                            continue
                except Exception:
                    continue

                return name

        # ---------------------------------
        # Prefix match
        # ---------------------------------

        for item in symbols:

            name = str(
                getattr(item, "name", "")
            ).strip()

            if not name:
                continue

            upper_name = name.upper()

            if upper_name.startswith(requested):

                try:
                    if not item.visible:
                        if not mt5.symbol_select(name, True):
                            continue
                except Exception:
                    continue

                return name

        return None

    # =====================================
    # SYMBOL INFORMATION
    # =====================================

    def _get_symbol_info(self, symbol: str):
        if not symbol:
            return None

        try:
            info = mt5.symbol_info(symbol)

            if info is None:
                return None

            if not info.visible:

                selected = mt5.symbol_select(
                    symbol,
                    True,
                )

                if not selected:
                    return None

                info = mt5.symbol_info(symbol)

            return info

        except Exception:
            return None

    # =====================================
    # TICK
    # =====================================

    def _get_tick(self, symbol: str):
        try:
            return mt5.symbol_info_tick(symbol)
        except Exception:
            return None

    # =====================================
    # SPREAD
    # =====================================

    def _calculate_spread_points(
        self,
        tick,
        symbol_info,
    ) -> Optional[Decimal]:

        if tick is None or symbol_info is None:
            return None

        point = self._decimal(
            getattr(symbol_info, "point", None)
        )

        bid = self._decimal(
            getattr(tick, "bid", None)
        )

        ask = self._decimal(
            getattr(tick, "ask", None)
        )

        if (
            point is None
            or point <= 0
            or bid is None
            or ask is None
        ):
            return None

        return abs(ask - bid) / point

    # =====================================
    # BROKER STOP DISTANCE
    # =====================================

    def _get_broker_stop_distance_points(
        self,
        symbol_info,
    ) -> Decimal:

        value = self._decimal(
            getattr(
                symbol_info,
                "trade_stops_level",
                0,
            )
        )

        if value is None or value < 0:
            return Decimal("0")

        return value

    # =====================================
    # PRICE DISTANCE
    # =====================================

    @staticmethod
    def _calculate_price_distance(
        entry: Decimal,
        price: Decimal,
    ) -> Decimal:

        return abs(entry - price)

    # =====================================
    # DISTANCE IN POINTS
    # =====================================

    def _calculate_distance_points(
        self,
        entry: Decimal,
        price: Decimal,
        symbol_info,
    ) -> Optional[Decimal]:

        point = self._decimal(
            getattr(symbol_info, "point", None)
        )

        if point is None or point <= 0:
            return None

        return abs(entry - price) / point

    # =====================================
    # RISK / REWARD
    # =====================================

    @staticmethod
    def _calculate_rr(
        entry: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
    ) -> Optional[Decimal]:

        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)

        if risk <= 0:
            return None

        return reward / risk

    # =====================================
    # TP SELECTION
    # =====================================

    def _select_take_profit(
        self,
        trade: Dict[str, Any],
        direction: str,
    ):

        candidates = [
            trade.get("take_profit_2"),
            trade.get("take_profit_1"),
            trade.get("take_profit"),
        ]

        valid = []

        for value in candidates:

            price = self._decimal(value)

            if price is not None:
                valid.append(price)

        if not valid:
            return None

        if direction == "buy":
            return max(valid)

        if direction == "sell":
            return min(valid)

        return None

    # =====================================
    # MAIN EVALUATION
    # =====================================

    def evaluate(
        self,
        trade: Dict[str, Any],
    ) -> Dict[str, Any]:

        rejection_reasons = []

        # =====================================
        # SIGNAL DATA
        # =====================================

        symbol = str(
            trade.get("symbol") or ""
        ).strip().upper()

        direction = self._normalize_direction(
            trade.get("direction")
        )

        confidence = self._decimal(
            trade.get("confidence")
        )

        if confidence is None:
            confidence = Decimal("0")

        setup_quality = self._normalize_quality(
            trade.get("setup_quality")
        )

        risk_percent = self._decimal(
            trade.get("risk_percent")
        )

        if risk_percent is None:
            risk_percent = self.DEFAULT_RISK_PERCENT

        entry = self._decimal(
            trade.get("entry_price")
        )

        stop_loss = self._decimal(
            trade.get("stop_loss")
        )

        selected_take_profit = self._select_take_profit(
            trade,
            direction,
        )

        tp1 = self._decimal(
            trade.get("take_profit_1")
        )

        tp2 = self._decimal(
            trade.get("take_profit_2")
        )

        rr_value = None
        stop_distance = None
        stop_distance_points = None
        spread_points = None
        broker_min_stop_points = None

        account_balance = None
        account_equity = None
        free_margin = None

        broker_symbol = None

        # =====================================
        # MT5 CONNECTION
        # =====================================

        if not self.ensure_mt5_connection():

            rejection_reasons.append(
                "MT5 connection failed"
            )

        # =====================================
        # ACCOUNT
        # =====================================

        account = self._get_account()

        if account is None:

            rejection_reasons.append(
                "MT5 account unavailable"
            )

        else:

            account_balance = self._decimal(
                getattr(
                    account,
                    "balance",
                    None,
                )
            )

            account_equity = self._decimal(
                getattr(
                    account,
                    "equity",
                    None,
                )
            )

            free_margin = self._decimal(
                getattr(
                    account,
                    "margin_free",
                    None,
                )
            )

            if free_margin is None:

                rejection_reasons.append(
                    "Free margin unavailable"
                )

            elif free_margin < self.MIN_FREE_MARGIN:

                rejection_reasons.append(
                    f"Low free margin ({free_margin})"
                )

            trade_allowed = getattr(
                account,
                "trade_allowed",
                True,
            )

            if not trade_allowed:

                rejection_reasons.append(
                    "MT5 account does not allow trading"
                )

        # =====================================
        # OPEN POSITIONS
        # =====================================

        positions = self._get_open_positions()

        open_positions_count = len(
            positions
        )

        if open_positions_count >= self.MAX_OPEN_TRADES:

            rejection_reasons.append(
                f"Maximum open trades reached "
                f"({open_positions_count}/{self.MAX_OPEN_TRADES})"
            )

        # =====================================
        # SYMBOL
        # =====================================

        symbol_info = None
        tick = None

        if not symbol:

            rejection_reasons.append(
                "Symbol missing"
            )

        else:

            broker_symbol = (
                self._resolve_broker_symbol(
                    symbol
                )
            )

            if broker_symbol is None:

                rejection_reasons.append(
                    f"Symbol {symbol} could not be resolved to a tradable MT5 broker symbol"
                )

            else:

                symbol_info = self._get_symbol_info(
                    broker_symbol
                )

                if symbol_info is None:

                    rejection_reasons.append(
                        f"Broker symbol {broker_symbol} unavailable from MT5"
                    )

                else:

                    tick = self._get_tick(
                        broker_symbol
                    )

                    if tick is None:

                        rejection_reasons.append(
                            f"Live tick unavailable for {broker_symbol}"
                        )

                    trade_mode = getattr(
                        symbol_info,
                        "trade_mode",
                        None,
                    )

                    if (
                        trade_mode
                        == mt5.SYMBOL_TRADE_MODE_DISABLED
                    ):

                        rejection_reasons.append(
                            f"{broker_symbol} trading is disabled by broker"
                        )

        # =====================================
        # SPREAD
        # =====================================

        if (
            symbol_info is not None
            and tick is not None
        ):

            spread_points = (
                self._calculate_spread_points(
                    tick,
                    symbol_info,
                )
            )

            if spread_points is None:

                rejection_reasons.append(
                    f"Unable to calculate {broker_symbol} spread"
                )

            elif spread_points > self.MAX_SPREAD_POINTS:

                rejection_reasons.append(
                    f"Spread too high "
                    f"({spread_points:.2f} points, "
                    f"maximum {self.MAX_SPREAD_POINTS} points)"
                )

        # =====================================
        # DIRECTION
        # =====================================

        if direction not in {"buy", "sell"}:

            rejection_reasons.append(
                "Invalid trade direction; expected buy/long or sell/short"
            )

        # =====================================
        # CONFIDENCE
        # =====================================

        if confidence < self.MIN_CONFIDENCE:

            rejection_reasons.append(
                f"Confidence too low "
                f"({confidence}%, minimum {self.MIN_CONFIDENCE}%)"
            )

        # =====================================
        # QUALITY
        # =====================================

        allowed_quality = {
            "very_strong",
            "strong",
            "high",
            "good",
            "moderate",
        }

        if setup_quality not in allowed_quality:

            rejection_reasons.append(
                f"Setup quality is not approved ({setup_quality})"
            )

        # =====================================
        # RISK
        # =====================================

        if risk_percent <= 0:

            rejection_reasons.append(
                "Risk percentage must be greater than zero"
            )

        elif risk_percent > self.MAX_RISK_PERCENT:

            rejection_reasons.append(
                f"Risk exceeds maximum allowed "
                f"({risk_percent}% > {self.MAX_RISK_PERCENT}%)"
            )

        # =====================================
        # PRICE VALIDATION
        # =====================================

        if entry is None:

            rejection_reasons.append(
                "Entry price is missing or invalid"
            )

        if stop_loss is None:

            rejection_reasons.append(
                "Stop loss is missing or invalid"
            )

        if selected_take_profit is None:

            rejection_reasons.append(
                "Take profit is missing or invalid"
            )

        # =====================================
        # GEOMETRY
        # =====================================

        if (
            entry is not None
            and stop_loss is not None
            and selected_take_profit is not None
        ):

            stop_distance = (
                self._calculate_price_distance(
                    entry,
                    stop_loss,
                )
            )

            if direction == "buy":

                if stop_loss >= entry:

                    rejection_reasons.append(
                        "BUY stop loss must be below entry"
                    )

                if selected_take_profit <= entry:

                    rejection_reasons.append(
                        "BUY take profit must be above entry"
                    )

            elif direction == "sell":

                if stop_loss <= entry:

                    rejection_reasons.append(
                        "SELL stop loss must be above entry"
                    )

                if selected_take_profit >= entry:

                    rejection_reasons.append(
                        "SELL take profit must be below entry"
                    )

            # =====================================
            # STOP DISTANCE
            # =====================================

            if symbol_info is not None:

                stop_distance_points = (
                    self._calculate_distance_points(
                        entry,
                        stop_loss,
                        symbol_info,
                    )
                )

                broker_min_stop_points = (
                    self._get_broker_stop_distance_points(
                        symbol_info,
                    )
                )

                if (
                    stop_distance_points is not None
                    and stop_distance_points
                    < self.MIN_STOP_DISTANCE_POINTS
                ):

                    rejection_reasons.append(
                        f"Stop distance too small "
                        f"({stop_distance_points:.2f} points, "
                        f"minimum {self.MIN_STOP_DISTANCE_POINTS} points)"
                    )

                if (
                    stop_distance_points is not None
                    and broker_min_stop_points > 0
                    and stop_distance_points
                    < broker_min_stop_points
                ):

                    rejection_reasons.append(
                        f"Stop distance violates broker minimum "
                        f"({stop_distance_points:.2f} points < "
                        f"{broker_min_stop_points:.2f} points)"
                    )

            # =====================================
            # RISK / REWARD
            # =====================================

            rr_value = self._calculate_rr(
                entry,
                stop_loss,
                selected_take_profit,
            )

            if rr_value is None:

                rejection_reasons.append(
                    "Unable to calculate risk/reward"
                )

            elif rr_value < self.MIN_RISK_REWARD:

                rejection_reasons.append(
                    f"Risk reward too low "
                    f"({rr_value:.2f}R, "
                    f"minimum {self.MIN_RISK_REWARD:.2f}R)"
                )

        # =====================================
        # TP DIAGNOSTICS
        # =====================================

        tp1_rr = None
        tp2_rr = None

        if (
            entry is not None
            and stop_loss is not None
        ):

            if tp1 is not None:

                tp1_rr = self._calculate_rr(
                    entry,
                    stop_loss,
                    tp1,
                )

            if tp2 is not None:

                tp2_rr = self._calculate_rr(
                    entry,
                    stop_loss,
                    tp2,
                )

        # =====================================
        # RESULT
        # =====================================

        approved = not rejection_reasons

        return {
            "approved": approved,
            "status": (
                "approved"
                if approved
                else "blocked"
            ),

            "reason": (
                None
                if approved
                else rejection_reasons[0]
            ),

            "reasons": rejection_reasons,

            "symbol": symbol,

            "broker_symbol": broker_symbol,

            "direction": direction,

            "confidence": float(confidence),

            "setup_quality": setup_quality,

            "risk_percent": float(risk_percent),

            "risk_reward": (
                float(rr_value)
                if rr_value is not None
                else None
            ),

            "tp1_risk_reward": (
                float(tp1_rr)
                if tp1_rr is not None
                else None
            ),

            "tp2_risk_reward": (
                float(tp2_rr)
                if tp2_rr is not None
                else None
            ),

            "entry_price": (
                float(entry)
                if entry is not None
                else None
            ),

            "stop_loss": (
                float(stop_loss)
                if stop_loss is not None
                else None
            ),

            "take_profit": (
                float(selected_take_profit)
                if selected_take_profit is not None
                else None
            ),

            "take_profit_1": (
                float(tp1)
                if tp1 is not None
                else None
            ),

            "take_profit_2": (
                float(tp2)
                if tp2 is not None
                else None
            ),

            "stop_distance": (
                float(stop_distance)
                if stop_distance is not None
                else None
            ),

            "stop_distance_points": (
                float(stop_distance_points)
                if stop_distance_points is not None
                else None
            ),

            "broker_min_stop_points": (
                float(broker_min_stop_points)
                if broker_min_stop_points is not None
                else None
            ),

            "spread_points": (
                float(spread_points)
                if spread_points is not None
                else None
            ),

            "account_balance": (
                float(account_balance)
                if account_balance is not None
                else None
            ),

            "account_equity": (
                float(account_equity)
                if account_equity is not None
                else None
            ),

            "free_margin": (
                float(free_margin)
                if free_margin is not None
                else None
            ),

            "open_positions": open_positions_count,

            "message": (
                "Trade passed MT5 risk gate"
                if approved
                else "Trade rejected by MT5 risk gate"
            ),
        }


# =====================================
# SINGLETON
# =====================================

risk_gate = RiskGate()