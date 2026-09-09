from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
import MetaTrader5 as mt5
from app.market_data_mt5.candle_adapter import mt5_candles_to_models
from app.market_data_mt5.candle_service import mt5_candle_service
from app.market_data_mt5.service import mt5_market_data_service

from app.mt5.connection import mt5_connection

from app.services.mt5_ai_market_analysis_service import (
    mt5_ai_market_analysis_service,
)
from app.services.mt5_multi_timeframe_service import (
    mt5_multi_timeframe_service,
)

from app.services.fvg_service import detect_fair_value_gaps
from app.services.liquidity_service import detect_liquidity_sweeps
from app.services.order_block_service import detect_order_blocks
from app.services.support_resistance_service import detect_support_resistance


class MT5TradeSetupError(RuntimeError):
    pass


@dataclass
class MT5TradeSetup:
    symbol: str
    timeframe: str
    mt5_symbol: str

    current_price: Decimal
    bid: Decimal
    ask: Decimal
    spread: Decimal

    signal: str
    direction: str
    setup_quality: str
    confidence: float

    setup_status: str
    next_action: str

    market_condition: str
    overall_bias: str

    entry_price: Decimal
    entry_zone_low: Decimal
    entry_zone_high: Decimal

    stop_loss: Decimal

    take_profit_1: Decimal
    take_profit_2: Decimal

    risk_reward_1: Decimal
    risk_reward_2: Decimal

    invalidation_price: Decimal

    confirmations: list[str]
    warnings: list[str]
    reasons: list[str]

    bullish_score: float
    bearish_score: float

    active_fvg_count: int
    active_order_block_count: int
    liquidity_sweep_count: int
    support_count: int
    resistance_count: int

    execution_zone_analysis: dict[str, Any]


class MT5TradeSetupService:

    # =========================================================
    # HARD SAFETY CEILINGS
    # =========================================================

    HARD_MAX_ENTRY_DISTANCE_PERCENT = Decimal("2.00")
    HARD_MAX_ZONE_WIDTH_PERCENT = Decimal("1.00")
    HARD_MAX_STOP_DISTANCE_PERCENT = Decimal("2.00")

    # =========================================================
    # VOLATILITY-ADJUSTED EXECUTION LIMITS
    #
    # IMPORTANT:
    # The volatility measure used by this service is the
    # recent average candle range, not a classical ATR.
    # =========================================================

    MAX_ZONE_WIDTH_VOLATILITY_MULTIPLE = Decimal("1.50")
    MAX_ENTRY_DISTANCE_VOLATILITY_MULTIPLE = Decimal("3.00")

    # =========================================================
    # RECENT MARKET EVIDENCE
    # =========================================================

    RECENT_FVG_CANDLES = 120
    RECENT_ORDER_BLOCK_CANDLES = 120
    RECENT_LIQUIDITY_CANDLES = 120

    # =========================================================
    # RISK / REWARD
    # =========================================================

    MIN_RISK_REWARD_1 = Decimal("1.50")
    MIN_RISK_REWARD_2 = Decimal("2.50")

    # =========================================================
    # STRUCTURAL BUFFER
    # =========================================================

    STRUCTURAL_BUFFER_PERCENT = Decimal("0.05")

    # =========================================================
    # VOLATILITY LOOKBACK
    # =========================================================

    VOLATILITY_LOOKBACK = 20

    # =========================================================
    # EXECUTION-ZONE COMBINATION
    # =========================================================

    MAX_ZONE_COMBINATION_GAP_PERCENT = Decimal("0.15")

    # =========================================================
    # PRICE ROUNDING
    # =========================================================

    DEFAULT_PRICE_DIGITS = 3

    # =========================================================
    # VALID TIMEFRAMES
    # =========================================================

    VALID_TIMEFRAMES = {
        "1m",
        "5m",
        "15m",
        "30m",
        "1h",
        "4h",
        "1d",
    }

    # =========================================================
    # BASIC HELPERS
    # =========================================================

    def _decimal(self, value: Any) -> Decimal:
        return Decimal(str(value))

    def _round_price(
        self,
        value: Decimal,
        digits: int = DEFAULT_PRICE_DIGITS,
    ) -> Decimal:
        quantum = Decimal("1").scaleb(-digits)

        return value.quantize(
            quantum,
            rounding=ROUND_HALF_UP,
        )

    def _get_broker_price_digits(
        self,
        mt5_symbol: str,
    ) -> int:
        """Return the exact price precision reported by MT5."""

        try:
            info = mt5.symbol_info(mt5_symbol)
            if info is not None:
                digits = int(getattr(info, "digits", -1))
                if digits >= 0:
                    return digits
        except Exception:
            pass

        return self.DEFAULT_PRICE_DIGITS

    def _market_direction_for_trade(
        self,
        trade_direction: str,
    ) -> str:
        """
        Convert execution direction into the directional
        vocabulary used by the structural evidence engines.

        Trade direction:
            long / short

        Evidence direction:
            bullish / bearish
        """

        if trade_direction == "long":
            return "bullish"

        if trade_direction == "short":
            return "bearish"

        return "neutral"

    # =========================================================
    # MT5 CONNECTION
    # =========================================================

    def _ensure_mt5_connection(self) -> None:
        """
        Ensure the application-level MT5 connection is active.

        This is important when the service is called directly from
        Python instead of through the /api/mt5/connect endpoint.

        The connection object maintains application-level state,
        while the MetaTrader5 package maintains the actual terminal
        connection.
        """

        if mt5_connection.is_connected():
            return

        try:
            result = mt5_connection.connect()

            if result is False:
                raise MT5TradeSetupError(
                    "MetaTrader 5 connection could not be established"
                )

        except MT5TradeSetupError:
            raise

        except Exception as exc:
            raise MT5TradeSetupError(
                f"MetaTrader 5 is not connected: {exc}"
            ) from exc

        if not mt5_connection.is_connected():
            raise MT5TradeSetupError(
                "MetaTrader 5 connection could not be established"
            )

    # =========================================================
    # MARKET DATA
    # =========================================================

    def _load_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ):
        try:
            raw_candles = mt5_candle_service.get_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )

            if not raw_candles:
                raise MT5TradeSetupError(
                    f"No MT5 candles available for "
                    f"{symbol} {timeframe}"
                )

            candles = mt5_candles_to_models(
                raw_candles
            )

            if not candles:
                raise MT5TradeSetupError(
                    f"MT5 candle conversion returned no "
                    f"usable candles for {symbol} {timeframe}"
                )

            return candles

        except MT5TradeSetupError:
            raise

        except Exception as exc:
            raise MT5TradeSetupError(
                f"Unable to load MT5 candles for "
                f"{symbol} {timeframe}: {exc}"
            ) from exc

    def _get_market(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        try:
            market = mt5_market_data_service.get_tick(
                symbol
            )

            if not market:
                raise MT5TradeSetupError(
                    f"No MT5 market data available for {symbol}"
                )

            required_fields = {
                "mt5_symbol",
                "bid",
                "ask",
                "spread",
            }

            missing = [
                field
                for field in required_fields
                if field not in market
            ]

            if missing:
                raise MT5TradeSetupError(
                    f"MT5 market data for {symbol} is missing "
                    f"required fields: {', '.join(missing)}"
                )

            return market

        except MT5TradeSetupError:
            raise

        except Exception as exc:
            raise MT5TradeSetupError(
                f"Unable to retrieve MT5 market price "
                f"for {symbol}: {exc}"
            ) from exc

    # =========================================================
    # VOLATILITY
    # =========================================================

    def _calculate_recent_volatility(
        self,
        candles,
    ) -> Decimal:
        """
        Calculate the average high-low range of the most
        recent candles.

        This is deliberately NOT called ATR because it does
        not use true range or Wilder smoothing.
        """

        if not candles:
            return Decimal("0")

        recent = candles[
            -self.VOLATILITY_LOOKBACK:
        ]

        ranges: list[Decimal] = []

        for candle in recent:
            high = self._decimal(candle.high)
            low = self._decimal(candle.low)

            candle_range = high - low

            if candle_range > 0:
                ranges.append(candle_range)

        if not ranges:
            return Decimal("0")

        return (
            sum(
                ranges,
                Decimal("0"),
            )
            / Decimal(len(ranges))
        )

    def _volatility_distance_percent(
        self,
        current_price: Decimal,
        volatility: Decimal,
    ) -> Decimal:
        if (
            current_price <= 0
            or volatility <= 0
        ):
            return Decimal("0")

        return (
            volatility
            / current_price
            * Decimal("100")
        )

    def _dynamic_entry_distance_percent(
        self,
        current_price: Decimal,
        volatility: Decimal,
    ) -> Decimal:
        volatility_percent = (
            self._volatility_distance_percent(
                current_price,
                volatility,
            )
        )

        dynamic_limit = (
            volatility_percent
            * self.MAX_ENTRY_DISTANCE_VOLATILITY_MULTIPLE
        )

        if dynamic_limit <= 0:
            dynamic_limit = Decimal("0.25")

        return min(
            dynamic_limit,
            self.HARD_MAX_ENTRY_DISTANCE_PERCENT,
        )

    def _dynamic_zone_width_percent(
        self,
        current_price: Decimal,
        volatility: Decimal,
    ) -> Decimal:
        volatility_percent = (
            self._volatility_distance_percent(
                current_price,
                volatility,
            )
        )

        dynamic_limit = (
            volatility_percent
            * self.MAX_ZONE_WIDTH_VOLATILITY_MULTIPLE
        )

        if dynamic_limit <= 0:
            dynamic_limit = Decimal("0.10")

        return min(
            dynamic_limit,
            self.HARD_MAX_ZONE_WIDTH_PERCENT,
        )

    # =========================================================
    # ZONE METRICS
    # =========================================================

    def _zone_width_percent(
        self,
        current_price: Decimal,
        lower: Decimal,
        upper: Decimal,
    ) -> Decimal:
        if current_price <= 0:
            return Decimal("100")

        if upper < lower:
            lower, upper = upper, lower

        return (
            (upper - lower)
            / current_price
            * Decimal("100")
        )

    def _zone_distance_percent(
        self,
        current_price: Decimal,
        lower: Decimal,
        upper: Decimal,
    ) -> Decimal:
        if current_price <= 0:
            return Decimal("100")

        if upper < lower:
            lower, upper = upper, lower

        if (
            lower
            <= current_price
            <= upper
        ):
            return Decimal("0")

        if current_price < lower:
            distance = (
                lower
                - current_price
            )
        else:
            distance = (
                current_price
                - upper
            )

        return (
            distance
            / current_price
            * Decimal("100")
        )

    def _zone_contains_price(
        self,
        current_price: Decimal,
        lower: Decimal,
        upper: Decimal,
    ) -> bool:
        if upper < lower:
            lower, upper = upper, lower

        return (
            lower
            <= current_price
            <= upper
        )

    # =========================================================
    # RECENCY
    # =========================================================

    def _zone_age(
        self,
        created_candle_index: int,
        candle_count: int,
    ) -> int:
        return max(
            0,
            candle_count
            - 1
            - created_candle_index,
        )

    def _zone_is_recent(
        self,
        created_candle_index: int,
        candle_count: int,
        max_age: int,
    ) -> bool:
        age = self._zone_age(
            created_candle_index,
            candle_count,
        )

        return age <= max_age

    # =========================================================
    # CANDIDATE SCORING
    # =========================================================

    def _candidate_zone_score(
        self,
        current_price: Decimal,
        lower: Decimal,
        upper: Decimal,
        created_candle_index: int,
        candle_count: int,
        max_age: int,
        dynamic_distance_limit: Decimal,
        dynamic_width_limit: Decimal,
    ) -> Decimal:

        distance = (
            self._zone_distance_percent(
                current_price,
                lower,
                upper,
            )
        )

        width = (
            self._zone_width_percent(
                current_price,
                lower,
                upper,
            )
        )

        age = self._zone_age(
            created_candle_index,
            candle_count,
        )

        if max_age > 0:
            recency_score = (
                Decimal("1")
                - (
                    Decimal(age)
                    / Decimal(max_age)
                )
            )
        else:
            recency_score = Decimal("0")

        recency_score = max(
            Decimal("0"),
            recency_score,
        )

        if dynamic_distance_limit > 0:
            proximity_score = max(
                Decimal("0"),
                Decimal("1")
                - (
                    distance
                    / dynamic_distance_limit
                ),
            )
        else:
            proximity_score = Decimal("0")

        if dynamic_width_limit > 0:
            width_score = max(
                Decimal("0"),
                Decimal("1")
                - (
                    width
                    / dynamic_width_limit
                ),
            )
        else:
            width_score = Decimal("0")

        inside_score = (
            Decimal("0.35")
            if self._zone_contains_price(
                current_price,
                lower,
                upper,
            )
            else Decimal("0")
        )

        return (
            proximity_score
            * Decimal("0.45")
            + recency_score
            * Decimal("0.25")
            + width_score
            * Decimal("0.15")
            + inside_score
        )

    # =========================================================
    # FVG DIAGNOSTICS
    #
    # direction here means EVIDENCE direction:
    # bullish / bearish
    # =========================================================

    def _analyze_fvg_candidates(
        self,
        fvgs,
        evidence_direction: str,
        current_price: Decimal,
        candle_count: int,
        dynamic_distance_limit: Decimal,
        dynamic_width_limit: Decimal,
    ) -> tuple[
        list[dict[str, Any]],
        dict[str, Any],
    ]:

        active = 0
        directional = 0
        recent = 0
        within_distance = 0
        acceptable_width = 0
        qualifying = 0

        candidates: list[dict[str, Any]] = []

        rejection_reasons = {
            "invalid_zone": 0,
            "not_recent": 0,
            "too_far": 0,
            "too_wide": 0,
            "too_far_and_too_wide": 0,
        }

        for fvg in fvgs:

            if fvg.mitigated:
                continue

            active += 1

            if (
                fvg.direction
                != evidence_direction
            ):
                continue

            directional += 1

            lower = self._decimal(
                fvg.lower_price
            )

            upper = self._decimal(
                fvg.upper_price
            )

            if (
                lower <= 0
                or upper <= lower
            ):
                rejection_reasons[
                    "invalid_zone"
                ] += 1

                continue

            age = self._zone_age(
                fvg.created_candle_index,
                candle_count,
            )

            if not self._zone_is_recent(
                fvg.created_candle_index,
                candle_count,
                self.RECENT_FVG_CANDLES,
            ):
                rejection_reasons[
                    "not_recent"
                ] += 1

                continue

            recent += 1

            distance = (
                self._zone_distance_percent(
                    current_price,
                    lower,
                    upper,
                )
            )

            width = (
                self._zone_width_percent(
                    current_price,
                    lower,
                    upper,
                )
            )

            distance_ok = (
                distance
                <= dynamic_distance_limit
            )

            width_ok = (
                width
                <= dynamic_width_limit
            )

            if distance_ok:
                within_distance += 1

            if width_ok:
                acceptable_width += 1

            if (
                not distance_ok
                and not width_ok
            ):
                rejection_reasons[
                    "too_far_and_too_wide"
                ] += 1

                continue

            if not distance_ok:
                rejection_reasons[
                    "too_far"
                ] += 1

                continue

            if not width_ok:
                rejection_reasons[
                    "too_wide"
                ] += 1

                continue

            qualifying += 1

            score = (
                self._candidate_zone_score(
                    current_price=current_price,
                    lower=lower,
                    upper=upper,
                    created_candle_index=(
                        fvg.created_candle_index
                    ),
                    candle_count=candle_count,
                    max_age=self.RECENT_FVG_CANDLES,
                    dynamic_distance_limit=(
                        dynamic_distance_limit
                    ),
                    dynamic_width_limit=(
                        dynamic_width_limit
                    ),
                )
            )

            candidates.append(
                {
                    "source": "fvg",
                    "direction": evidence_direction,
                    "lower": lower,
                    "upper": upper,
                    "width_percent": width,
                    "distance_percent": distance,
                    "age_candles": age,
                    "created_candle_index": (
                        fvg.created_candle_index
                    ),
                    "created_time": fvg.created_time,
                    "score": score,
                }
            )

        candidates.sort(
            key=lambda item: (
                item["score"],
                -item["age_candles"],
            ),
            reverse=True,
        )

        diagnostics = {
            "active": active,
            "directional": directional,
            "recent": recent,
            "within_distance": within_distance,
            "acceptable_width": acceptable_width,
            "qualifying": qualifying,
            "rejections": rejection_reasons,
        }

        return (
            candidates,
            diagnostics,
        )

    # =========================================================
    # ORDER BLOCK DIAGNOSTICS
    #
    # direction here means EVIDENCE direction:
    # bullish / bearish
    # =========================================================

    def _analyze_order_block_candidates(
        self,
        order_blocks,
        evidence_direction: str,
        current_price: Decimal,
        candle_count: int,
        dynamic_distance_limit: Decimal,
        dynamic_width_limit: Decimal,
    ) -> tuple[
        list[dict[str, Any]],
        dict[str, Any],
    ]:

        active = 0
        directional = 0
        recent = 0
        within_distance = 0
        acceptable_width = 0
        qualifying = 0

        candidates: list[dict[str, Any]] = []

        rejection_reasons = {
            "invalid_zone": 0,
            "not_recent": 0,
            "too_far": 0,
            "too_wide": 0,
            "too_far_and_too_wide": 0,
        }

        for block in order_blocks:

            if block.mitigated:
                continue

            active += 1

            if (
                block.direction
                != evidence_direction
            ):
                continue

            directional += 1

            lower = self._decimal(
                block.lower_price
            )

            upper = self._decimal(
                block.upper_price
            )

            if (
                lower <= 0
                or upper <= lower
            ):
                rejection_reasons[
                    "invalid_zone"
                ] += 1

                continue

            age = self._zone_age(
                block.created_candle_index,
                candle_count,
            )

            if not self._zone_is_recent(
                block.created_candle_index,
                candle_count,
                self.RECENT_ORDER_BLOCK_CANDLES,
            ):
                rejection_reasons[
                    "not_recent"
                ] += 1

                continue

            recent += 1

            distance = (
                self._zone_distance_percent(
                    current_price,
                    lower,
                    upper,
                )
            )

            width = (
                self._zone_width_percent(
                    current_price,
                    lower,
                    upper,
                )
            )

            distance_ok = (
                distance
                <= dynamic_distance_limit
            )

            width_ok = (
                width
                <= dynamic_width_limit
            )

            if distance_ok:
                within_distance += 1

            if width_ok:
                acceptable_width += 1

            if (
                not distance_ok
                and not width_ok
            ):
                rejection_reasons[
                    "too_far_and_too_wide"
                ] += 1

                continue

            if not distance_ok:
                rejection_reasons[
                    "too_far"
                ] += 1

                continue

            if not width_ok:
                rejection_reasons[
                    "too_wide"
                ] += 1

                continue

            qualifying += 1

            score = (
                self._candidate_zone_score(
                    current_price=current_price,
                    lower=lower,
                    upper=upper,
                    created_candle_index=(
                        block.created_candle_index
                    ),
                    candle_count=candle_count,
                    max_age=(
                        self.RECENT_ORDER_BLOCK_CANDLES
                    ),
                    dynamic_distance_limit=(
                        dynamic_distance_limit
                    ),
                    dynamic_width_limit=(
                        dynamic_width_limit
                    ),
                )
            )

            candidates.append(
                {
                    "source": "order_block",
                    "direction": evidence_direction,
                    "lower": lower,
                    "upper": upper,
                    "width_percent": width,
                    "distance_percent": distance,
                    "age_candles": age,
                    "created_candle_index": (
                        block.created_candle_index
                    ),
                    "created_time": block.created_time,
                    "score": score,
                }
            )

        candidates.sort(
            key=lambda item: (
                item["score"],
                -item["age_candles"],
            ),
            reverse=True,
        )

        diagnostics = {
            "active": active,
            "directional": directional,
            "recent": recent,
            "within_distance": within_distance,
            "acceptable_width": acceptable_width,
            "qualifying": qualifying,
            "rejections": rejection_reasons,
        }

        return (
            candidates,
            diagnostics,
        )

    # =========================================================
    # ZONE COMBINATION
    # =========================================================

    def _zones_overlap_or_are_close(
        self,
        current_price: Decimal,
        first: dict[str, Any],
        second: dict[str, Any],
    ) -> bool:

        first_lower = first["lower"]
        first_upper = first["upper"]

        second_lower = second["lower"]
        second_upper = second["upper"]

        if (
            first_lower <= second_upper
            and second_lower <= first_upper
        ):
            return True

        if first_upper < second_lower:
            gap = (
                second_lower
                - first_upper
            )
        else:
            gap = (
                first_lower
                - second_upper
            )

        if current_price <= 0:
            return False

        gap_percent = (
            gap
            / current_price
            * Decimal("100")
        )

        return (
            gap_percent
            <= self.MAX_ZONE_COMBINATION_GAP_PERCENT
        )

    # =========================================================
    # SERIALIZE CANDIDATE
    # =========================================================

    def _serialize_candidate(
        self,
        candidate: dict[str, Any],
    ) -> dict[str, Any]:

        return {
            "source": candidate["source"],
            "direction": candidate["direction"],
            "lower": candidate["lower"],
            "upper": candidate["upper"],
            "width_percent": candidate[
                "width_percent"
            ],
            "distance_percent": candidate[
                "distance_percent"
            ],
            "age_candles": candidate[
                "age_candles"
            ],
            "created_candle_index": candidate[
                "created_candle_index"
            ],
            "created_time": candidate[
                "created_time"
            ],
            "score": candidate["score"],
        }

    # =========================================================
    # DIRECTION DIAGNOSTICS
    # =========================================================

    def _build_direction_diagnostics(
        self,
        fvgs,
        order_blocks,
        trade_direction: str,
        current_price: Decimal,
        candle_count: int,
        dynamic_distance_limit: Decimal,
        dynamic_width_limit: Decimal,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[str, Any],
    ]:

        evidence_direction = (
            self._market_direction_for_trade(
                trade_direction
            )
        )

        if evidence_direction == "neutral":
            raise MT5TradeSetupError(
                "Directional diagnostics require "
                "either long or short trade direction"
            )

        (
            fvg_candidates,
            fvg_diagnostics,
        ) = self._analyze_fvg_candidates(
            fvgs=fvgs,
            evidence_direction=evidence_direction,
            current_price=current_price,
            candle_count=candle_count,
            dynamic_distance_limit=(
                dynamic_distance_limit
            ),
            dynamic_width_limit=(
                dynamic_width_limit
            ),
        )

        (
            ob_candidates,
            ob_diagnostics,
        ) = self._analyze_order_block_candidates(
            order_blocks=order_blocks,
            evidence_direction=evidence_direction,
            current_price=current_price,
            candle_count=candle_count,
            dynamic_distance_limit=(
                dynamic_distance_limit
            ),
            dynamic_width_limit=(
                dynamic_width_limit
            ),
        )

        diagnostics = {
            "direction": trade_direction,

            "evidence_direction": evidence_direction,

            "fvg": fvg_diagnostics,

            "order_blocks": ob_diagnostics,

            "top_fvg_candidates": [
                self._serialize_candidate(
                    candidate
                )
                for candidate in fvg_candidates[:5]
            ],

            "top_order_block_candidates": [
                self._serialize_candidate(
                    candidate
                )
                for candidate in ob_candidates[:5]
            ],

            "selected_sources": [],

            "selected_candidates": [],

            "selection_status": (
                "no_qualifying_candidates"
                if not (
                    fvg_candidates
                    or ob_candidates
                )
                else "qualifying_candidates_available"
            ),
        }

        return (
            fvg_candidates,
            ob_candidates,
            diagnostics,
        )

    # =========================================================
    # EXECUTION ZONE SELECTION
    # =========================================================

    def _select_execution_zone(
        self,
        current_price: Decimal,
        fvgs,
        order_blocks,
        trade_direction: str,
        candle_count: int,
        volatility: Decimal,
    ) -> tuple[
        Decimal,
        Decimal,
        list[str],
        dict[str, Any],
    ]:

        if trade_direction not in {
            "long",
            "short",
        }:
            raise MT5TradeSetupError(
                "Execution zone selection requires "
                "a long or short trade direction"
            )

        evidence_direction = (
            self._market_direction_for_trade(
                trade_direction
            )
        )

        dynamic_distance_limit = (
            self._dynamic_entry_distance_percent(
                current_price,
                volatility,
            )
        )

        dynamic_width_limit = (
            self._dynamic_zone_width_percent(
                current_price,
                volatility,
            )
        )

        volatility_percent = (
            self._volatility_distance_percent(
                current_price,
                volatility,
            )
        )

        (
            fvg_candidates,
            ob_candidates,
            direction_diagnostics,
        ) = self._build_direction_diagnostics(
            fvgs=fvgs,
            order_blocks=order_blocks,
            trade_direction=trade_direction,
            current_price=current_price,
            candle_count=candle_count,
            dynamic_distance_limit=(
                dynamic_distance_limit
            ),
            dynamic_width_limit=(
                dynamic_width_limit
            ),
        )

        execution_zone_analysis: dict[str, Any] = {
            "volatility": volatility,

            "volatility_percent": volatility_percent,

            "volatility_method": (
                "recent_average_candle_range"
            ),

            "volatility_lookback": (
                self.VOLATILITY_LOOKBACK
            ),

            "dynamic_entry_distance_percent": (
                dynamic_distance_limit
            ),

            "dynamic_zone_width_percent": (
                dynamic_width_limit
            ),

            "hard_max_entry_distance_percent": (
                self.HARD_MAX_ENTRY_DISTANCE_PERCENT
            ),

            "hard_max_zone_width_percent": (
                self.HARD_MAX_ZONE_WIDTH_PERCENT
            ),

            "hard_max_stop_distance_percent": (
                self.HARD_MAX_STOP_DISTANCE_PERCENT
            ),

            "direction": trade_direction,

            "evidence_direction": evidence_direction,

            "candle_count": candle_count,

            "fvg": direction_diagnostics[
                "fvg"
            ],

            "order_blocks": (
                direction_diagnostics[
                    "order_blocks"
                ]
            ),

            "top_fvg_candidates": (
                direction_diagnostics[
                    "top_fvg_candidates"
                ]
            ),

            "top_order_block_candidates": (
                direction_diagnostics[
                    "top_order_block_candidates"
                ]
            ),

            "selected_sources": [],

            "selected_candidates": [],

            "selection_status": (
                "no_qualifying_candidates"
            ),
        }

        all_candidates = (
            fvg_candidates
            + ob_candidates
        )

        all_candidates.sort(
            key=lambda item: (
                item["score"],
                -item["age_candles"],
            ),
            reverse=True,
        )

        if not all_candidates:

            fvg_diagnostics = (
                execution_zone_analysis["fvg"]
            )

            ob_diagnostics = (
                execution_zone_analysis[
                    "order_blocks"
                ]
            )

            directional_recent_count = (
                fvg_diagnostics["recent"]
                + ob_diagnostics["recent"]
            )

            directional_active_count = (
                fvg_diagnostics["directional"]
                + ob_diagnostics["directional"]
            )

            within_distance_count = (
                fvg_diagnostics["within_distance"]
                + ob_diagnostics["within_distance"]
            )

            execution_zone_analysis[
                "selection_status"
            ] = "no_qualifying_candidates"

            if (
                directional_recent_count > 0
                and within_distance_count == 0
            ):
                execution_zone_analysis[
                    "waiting_status"
                ] = "waiting_for_price_to_reach_zone"

                execution_zone_analysis[
                    "waiting_reason"
                ] = (
                    "Recent directional execution evidence "
                    "exists, but all qualifying zones are "
                    "outside the current volatility-adjusted "
                    "entry distance"
                )

            elif (
                directional_active_count > 0
                and directional_recent_count == 0
            ):
                execution_zone_analysis[
                    "waiting_status"
                ] = "waiting_for_new_execution_evidence"

                execution_zone_analysis[
                    "waiting_reason"
                ] = (
                    "Directional execution evidence exists, "
                    "but no directional FVG or order block "
                    "is recent enough for execution"
                )

            elif directional_active_count == 0:
                execution_zone_analysis[
                    "waiting_status"
                ] = "no_directional_execution_evidence"

                execution_zone_analysis[
                    "waiting_reason"
                ] = (
                    "No active directional FVG or order block "
                    "currently supports the MTF trading bias"
                )

            else:
                execution_zone_analysis[
                    "waiting_status"
                ] = "execution_zone_not_confirmed"

                execution_zone_analysis[
                    "waiting_reason"
                ] = (
                    "Directional execution evidence is present "
                    "but does not currently satisfy all "
                    "execution-zone validation rules"
                )

            return (
                Decimal("0"),
                Decimal("0"),
                [],
                execution_zone_analysis,
            )

        primary = all_candidates[0]

        selected = [
            primary
        ]

        for candidate in all_candidates[1:]:

            if (
                candidate["source"]
                == primary["source"]
            ):
                continue

            if self._zones_overlap_or_are_close(
                current_price=current_price,
                first=primary,
                second=candidate,
            ):
                selected.append(
                    candidate
                )

                break

        lower = min(
            item["lower"]
            for item in selected
        )

        upper = max(
            item["upper"]
            for item in selected
        )

        final_width = (
            self._zone_width_percent(
                current_price,
                lower,
                upper,
            )
        )

        final_distance = (
            self._zone_distance_percent(
                current_price,
                lower,
                upper,
            )
        )

        combined_zone_valid = (
            final_distance
            <= dynamic_distance_limit
            and final_distance
            <= self.HARD_MAX_ENTRY_DISTANCE_PERCENT
            and final_width
            <= dynamic_width_limit
            and final_width
            <= self.HARD_MAX_ZONE_WIDTH_PERCENT
        )

        if not combined_zone_valid:

            lower = primary["lower"]
            upper = primary["upper"]

            final_width = (
                self._zone_width_percent(
                    current_price,
                    lower,
                    upper,
                )
            )

            final_distance = (
                self._zone_distance_percent(
                    current_price,
                    lower,
                    upper,
                )
            )

            selected = [
                primary
            ]

            execution_zone_analysis[
                "combination_status"
            ] = "combined_zone_failed_final_validation"

        else:

            execution_zone_analysis[
                "combination_status"
            ] = (
                "combined_zone_valid"
                if len(selected) > 1
                else "single_zone"
            )

        single_zone_valid = (
            final_distance
            <= dynamic_distance_limit
            and final_distance
            <= self.HARD_MAX_ENTRY_DISTANCE_PERCENT
            and final_width
            <= dynamic_width_limit
            and final_width
            <= self.HARD_MAX_ZONE_WIDTH_PERCENT
        )

        if not single_zone_valid:

            execution_zone_analysis[
                "selection_status"
            ] = (
                "selected_candidate_failed_final_validation"
            )

            execution_zone_analysis[
                "waiting_status"
            ] = "waiting_for_price_to_reach_zone"

            execution_zone_analysis[
                "waiting_reason"
            ] = (
                "The strongest directional execution zone "
                "exists but is outside the permitted "
                "volatility-adjusted execution distance"
            )

            execution_zone_analysis[
                "candidate_failure"
            ] = {
                "reason": (
                    "The strongest qualifying candidate "
                    "did not satisfy final execution-zone "
                    "validation"
                ),
                "final_width_percent": final_width,
                "final_distance_percent": final_distance,
            }

            return (
                Decimal("0"),
                Decimal("0"),
                [],
                execution_zone_analysis,
            )

        execution_zone_analysis[
            "selection_status"
        ] = "selected"

        execution_zone_analysis[
            "waiting_status"
        ] = "zone_ready"

        execution_zone_analysis[
            "waiting_reason"
        ] = None

        execution_zone_analysis[
            "selected_sources"
        ] = [
            item["source"]
            for item in selected
        ]

        execution_zone_analysis[
            "selected_candidates"
        ] = [
            self._serialize_candidate(
                item
            )
            for item in selected
        ]

        execution_zone_analysis[
            "selected_zone"
        ] = {
            "low": lower,
            "high": upper,
            "width_percent": final_width,
            "distance_percent": final_distance,
        }

        return (
            lower,
            upper,
            [
                item["source"]
                for item in selected
            ],
            execution_zone_analysis,
        )

    # =========================================================
    # NEUTRAL MARKET DIAGNOSTICS
    # =========================================================

    def _build_neutral_execution_zone_analysis(
        self,
        current_price: Decimal,
        candles,
        fvgs,
        order_blocks,
        volatility: Decimal,
    ) -> dict[str, Any]:

        candle_count = len(candles)

        dynamic_distance_limit = (
            self._dynamic_entry_distance_percent(
                current_price,
                volatility,
            )
        )

        dynamic_width_limit = (
            self._dynamic_zone_width_percent(
                current_price,
                volatility,
            )
        )

        volatility_percent = (
            self._volatility_distance_percent(
                current_price,
                volatility,
            )
        )

        (
            _bullish_fvgs,
            _bullish_obs,
            bullish_diagnostics,
        ) = self._build_direction_diagnostics(
            fvgs=fvgs,
            order_blocks=order_blocks,
            trade_direction="long",
            current_price=current_price,
            candle_count=candle_count,
            dynamic_distance_limit=(
                dynamic_distance_limit
            ),
            dynamic_width_limit=(
                dynamic_width_limit
            ),
        )

        (
            _bearish_fvgs,
            _bearish_obs,
            bearish_diagnostics,
        ) = self._build_direction_diagnostics(
            fvgs=fvgs,
            order_blocks=order_blocks,
            trade_direction="short",
            current_price=current_price,
            candle_count=candle_count,
            dynamic_distance_limit=(
                dynamic_distance_limit
            ),
            dynamic_width_limit=(
                dynamic_width_limit
            ),
        )

        return {
            "volatility": volatility,

            "volatility_percent": volatility_percent,

            "volatility_method": (
                "recent_average_candle_range"
            ),

            "volatility_lookback": (
                self.VOLATILITY_LOOKBACK
            ),

            "dynamic_entry_distance_percent": (
                dynamic_distance_limit
            ),

            "dynamic_zone_width_percent": (
                dynamic_width_limit
            ),

            "hard_max_entry_distance_percent": (
                self.HARD_MAX_ENTRY_DISTANCE_PERCENT
            ),

            "hard_max_zone_width_percent": (
                self.HARD_MAX_ZONE_WIDTH_PERCENT
            ),

            "hard_max_stop_distance_percent": (
                self.HARD_MAX_STOP_DISTANCE_PERCENT
            ),

            "direction": "neutral",

            "evidence_direction": "neutral",

            "candle_count": candle_count,

            "long": {
                "direction": "long",
                "evidence_direction": "bullish",

                "fvg": bullish_diagnostics[
                    "fvg"
                ],

                "order_blocks": (
                    bullish_diagnostics[
                        "order_blocks"
                    ]
                ),

                "top_fvg_candidates": (
                    bullish_diagnostics[
                        "top_fvg_candidates"
                    ]
                ),

                "top_order_block_candidates": (
                    bullish_diagnostics[
                        "top_order_block_candidates"
                    ]
                ),

                "selected_sources": [],

                "selected_candidates": [],

                "selection_status": (
                    bullish_diagnostics[
                        "selection_status"
                    ]
                ),
            },

            "short": {
                "direction": "short",
                "evidence_direction": "bearish",

                "fvg": bearish_diagnostics[
                    "fvg"
                ],

                "order_blocks": (
                    bearish_diagnostics[
                        "order_blocks"
                    ]
                ),

                "top_fvg_candidates": (
                    bearish_diagnostics[
                        "top_fvg_candidates"
                    ]
                ),

                "top_order_block_candidates": (
                    bearish_diagnostics[
                        "top_order_block_candidates"
                    ]
                ),

                "selected_sources": [],

                "selected_candidates": [],

                "selection_status": (
                    bearish_diagnostics[
                        "selection_status"
                    ]
                ),
            },

            "selected_sources": [],

            "selected_candidates": [],

            "selection_status": (
                "directional_bias_required"
            ),

            "waiting_status": (
                "directional_bias_required"
            ),

            "waiting_reason": (
                "No directional execution can be selected "
                "while the multi-timeframe bias is neutral"
            ),
        }

    # =========================================================
    # ENTRY
    # =========================================================

    def _calculate_entry_price(
        self,
        current_price: Decimal,
        direction: str,
        zone_low: Decimal,
        zone_high: Decimal,
    ) -> Decimal:

        if (
            zone_low <= 0
            or zone_high <= 0
            or zone_high <= zone_low
        ):
            return Decimal("0")

        if direction == "long":

            if zone_high <= current_price:
                return zone_high

            if zone_low <= current_price:
                return current_price

            return zone_low

        if direction == "short":

            if zone_low >= current_price:
                return zone_low

            if (
                zone_low
                <= current_price
                <= zone_high
            ):
                return current_price

            return zone_high

        return Decimal("0")

    # =========================================================
    # SUPPORT / RESISTANCE
    # =========================================================

    def _nearest_support(
        self,
        levels,
        price: Decimal,
    ):

        candidates = [
            level
            for level in levels
            if (
                level.type == "support"
                and not level.broken
                and self._decimal(
                    level.price
                ) < price
            )
        ]

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda level:
                self._decimal(
                    level.price
                ),
        )

    def _nearest_resistance(
        self,
        levels,
        price: Decimal,
    ):

        candidates = [
            level
            for level in levels
            if (
                level.type == "resistance"
                and not level.broken
                and self._decimal(
                    level.price
                ) > price
            )
        ]

        if not candidates:
            return None

        return min(
            candidates,
            key=lambda level:
                self._decimal(
                    level.price
                ),
        )

    # =========================================================
    # STOP LOSS
    # =========================================================

    def _calculate_stop_loss(
        self,
        direction: str,
        entry_price: Decimal,
        zone_low: Decimal,
        zone_high: Decimal,
        support_levels,
        resistance_levels,
    ) -> Decimal:

        if entry_price <= 0:
            return Decimal("0")

        if direction == "long":

            candidates = [
                zone_low
            ]

            support = (
                self._nearest_support(
                    support_levels,
                    entry_price,
                )
            )

            if support is not None:

                support_price = (
                    self._decimal(
                        support.price
                    )
                )

                if support_price < entry_price:
                    candidates.append(
                        support_price
                    )

            valid = [
                price
                for price in candidates
                if (
                    price > 0
                    and price < entry_price
                )
            ]

            if not valid:
                return Decimal("0")

            structural_stop = max(
                valid
            )

            stop = (
                structural_stop
                * (
                    Decimal("1")
                    - (
                        self.STRUCTURAL_BUFFER_PERCENT
                        / Decimal("100")
                    )
                )
            )

            if stop >= entry_price:
                return Decimal("0")

            return stop

        if direction == "short":

            candidates = [
                zone_high
            ]

            resistance = (
                self._nearest_resistance(
                    resistance_levels,
                    entry_price,
                )
            )

            if resistance is not None:

                resistance_price = (
                    self._decimal(
                        resistance.price
                    )
                )

                if resistance_price > entry_price:
                    candidates.append(
                        resistance_price
                    )

            valid = [
                price
                for price in candidates
                if price > entry_price
            ]

            if not valid:
                return Decimal("0")

            structural_stop = min(
                valid
            )

            stop = (
                structural_stop
                * (
                    Decimal("1")
                    + (
                        self.STRUCTURAL_BUFFER_PERCENT
                        / Decimal("100")
                    )
                )
            )

            if stop <= entry_price:
                return Decimal("0")

            return stop

        return Decimal("0")

    # =========================================================
    # RISK / REWARD
    # =========================================================

    def _calculate_risk_reward(
        self,
        direction: str,
        entry_price: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
    ) -> Decimal:

        if (
            entry_price <= 0
            or stop_loss <= 0
            or take_profit <= 0
        ):
            return Decimal("0")

        if direction == "long":

            risk = (
                entry_price
                - stop_loss
            )

            reward = (
                take_profit
                - entry_price
            )

        elif direction == "short":

            risk = (
                stop_loss
                - entry_price
            )

            reward = (
                entry_price
                - take_profit
            )

        else:
            return Decimal("0")

        if (
            risk <= 0
            or reward <= 0
        ):
            return Decimal("0")

        return reward / risk

    # =========================================================
    # TARGETS
    # =========================================================

    def _calculate_targets(
        self,
        direction: str,
        entry_price: Decimal,
        stop_loss: Decimal,
        support_levels,
        resistance_levels,
    ) -> tuple[
        Decimal,
        Decimal,
        dict[str, Any],
    ]:
        """
        Select TP1 and TP2 only from real opposing structural levels.

        The method also returns diagnostics so a rejected setup explains
        whether the failure was caused by missing structure, insufficient
        TP1 distance, or the absence of a distinct TP2.
        """

        diagnostics: dict[str, Any] = {
            "direction": direction,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "risk": Decimal("0"),
            "minimum_tp1": Decimal("0"),
            "minimum_tp2": Decimal("0"),
            "opposing_levels_found": 0,
            "opposing_levels": [],
            "tp1_candidates": [],
            "tp2_candidates": [],
            "selected_tp1": Decimal("0"),
            "selected_tp2": Decimal("0"),
            "status": "invalid_risk_structure",
            "rejection_reason": None,
        }

        if entry_price <= 0 or stop_loss <= 0:
            diagnostics["rejection_reason"] = "Invalid entry or stop-loss price"
            return Decimal("0"), Decimal("0"), diagnostics

        if direction == "long":
            risk = entry_price - stop_loss
            diagnostics["risk"] = risk

            if risk <= 0:
                diagnostics["rejection_reason"] = "Long stop-loss is not below entry"
                return Decimal("0"), Decimal("0"), diagnostics

            minimum_tp1 = entry_price + risk * self.MIN_RISK_REWARD_1
            minimum_tp2 = entry_price + risk * self.MIN_RISK_REWARD_2
            diagnostics["minimum_tp1"] = minimum_tp1
            diagnostics["minimum_tp2"] = minimum_tp2

            resistance_prices = sorted(set(
                self._decimal(level.price)
                for level in resistance_levels
                if (
                    level.type == "resistance"
                    and not level.broken
                    and self._decimal(level.price) > entry_price
                )
            ))

            diagnostics["opposing_levels_found"] = len(resistance_prices)
            diagnostics["opposing_levels"] = resistance_prices

            if not resistance_prices:
                diagnostics["status"] = "no_opposing_structural_levels"
                diagnostics["rejection_reason"] = (
                    "No unbroken resistance levels exist above the long entry"
                )
                return Decimal("0"), Decimal("0"), diagnostics

            tp1_candidates = [p for p in resistance_prices if p >= minimum_tp1]
            diagnostics["tp1_candidates"] = tp1_candidates

            if not tp1_candidates:
                diagnostics["status"] = "tp1_requirement_not_met"
                diagnostics["rejection_reason"] = (
                    "No opposing resistance level reaches the required 1.50R TP1 distance"
                )
                return Decimal("0"), Decimal("0"), diagnostics

            tp1 = tp1_candidates[0]

            tp2_candidates = [
                p for p in resistance_prices
                if p > tp1 and p >= minimum_tp2
            ]
            diagnostics["tp2_candidates"] = tp2_candidates

            if not tp2_candidates:
                diagnostics["status"] = "tp2_requirement_not_met"
                diagnostics["rejection_reason"] = (
                    "TP1 is valid, but no distinct opposing resistance level reaches the required 2.50R TP2 distance"
                )
                diagnostics["selected_tp1"] = tp1
                return Decimal("0"), Decimal("0"), diagnostics

            tp2 = tp2_candidates[0]
            diagnostics["selected_tp1"] = tp1
            diagnostics["selected_tp2"] = tp2
            diagnostics["status"] = "targets_selected"
            return tp1, tp2, diagnostics

        if direction == "short":
            risk = stop_loss - entry_price
            diagnostics["risk"] = risk

            if risk <= 0:
                diagnostics["rejection_reason"] = "Short stop-loss is not above entry"
                return Decimal("0"), Decimal("0"), diagnostics

            minimum_tp1 = entry_price - risk * self.MIN_RISK_REWARD_1
            minimum_tp2 = entry_price - risk * self.MIN_RISK_REWARD_2
            diagnostics["minimum_tp1"] = minimum_tp1
            diagnostics["minimum_tp2"] = minimum_tp2

            support_prices = sorted(set(
                self._decimal(level.price)
                for level in support_levels
                if (
                    level.type == "support"
                    and not level.broken
                    and self._decimal(level.price) < entry_price
                )
            ), reverse=True)

            diagnostics["opposing_levels_found"] = len(support_prices)
            diagnostics["opposing_levels"] = support_prices

            if not support_prices:
                diagnostics["status"] = "no_opposing_structural_levels"
                diagnostics["rejection_reason"] = (
                    "No unbroken support levels exist below the short entry"
                )
                return Decimal("0"), Decimal("0"), diagnostics

            tp1_candidates = [p for p in support_prices if p <= minimum_tp1]
            diagnostics["tp1_candidates"] = tp1_candidates

            if not tp1_candidates:
                diagnostics["status"] = "tp1_requirement_not_met"
                diagnostics["rejection_reason"] = (
                    "No opposing support level reaches the required 1.50R TP1 distance"
                )
                return Decimal("0"), Decimal("0"), diagnostics

            tp1 = tp1_candidates[0]

            tp2_candidates = [
                p for p in support_prices
                if p < tp1 and p <= minimum_tp2
            ]
            diagnostics["tp2_candidates"] = tp2_candidates

            if not tp2_candidates:
                diagnostics["status"] = "tp2_requirement_not_met"
                diagnostics["rejection_reason"] = (
                    "TP1 is valid, but no distinct opposing support level reaches the required 2.50R TP2 distance"
                )
                diagnostics["selected_tp1"] = tp1
                return Decimal("0"), Decimal("0"), diagnostics

            tp2 = tp2_candidates[0]
            diagnostics["selected_tp1"] = tp1
            diagnostics["selected_tp2"] = tp2
            diagnostics["status"] = "targets_selected"
            return tp1, tp2, diagnostics

        diagnostics["rejection_reason"] = f"Unsupported trade direction: {direction}"
        return Decimal("0"), Decimal("0"), diagnostics

    def _validate_final_price_geometry(
        self,
        direction: str,
        entry_price: Decimal,
        stop_loss: Decimal,
        take_profit_1: Decimal,
        take_profit_2: Decimal,
    ) -> tuple[bool, str | None]:
        """Validate final broker-rounded trade geometry."""

        values = (entry_price, stop_loss, take_profit_1, take_profit_2)

        if any(value <= 0 for value in values):
            return False, "All final trade prices must be positive"

        if direction == "long":
            if not (stop_loss < entry_price < take_profit_1 < take_profit_2):
                return False, "Long geometry must satisfy SL < Entry < TP1 < TP2"
            return True, None

        if direction == "short":
            if not (stop_loss > entry_price > take_profit_1 > take_profit_2):
                return False, "Short geometry must satisfy SL > Entry > TP1 > TP2"
            return True, None

        return False, f"Unsupported trade direction: {direction}"

    # =========================================================
    # NO TRADE / WAITING RESPONSE
    # =========================================================

    def _build_no_trade_setup(
        self,
        symbol: str,
        timeframe: str,
        mt5_symbol: str,
        market: dict[str, Any],
        market_analysis: Any,
        overall_bias: str,
        reason: str,
        evidence: dict[str, int],
        execution_zone_analysis: (
            dict[str, Any] | None
        ) = None,
        reasons: list[str] | None = None,
        warnings: list[str] | None = None,
        setup_status: str = "no_trade",
        next_action: str = "do_not_trade",
    ) -> MT5TradeSetup:

        current_price = self._decimal(
            market["ask"]
        )

        final_reasons = (
            reasons
            if reasons is not None
            else [
                reason,
                (
                    "No executable trade setup satisfies "
                    "the market-structure, execution-zone, "
                    "and risk validation rules"
                ),
            ]
        )

        final_warnings = (
            warnings
            if warnings is not None
            else [
                reason
            ]
        )

        return MT5TradeSetup(
            symbol=symbol,

            timeframe=timeframe,

            mt5_symbol=mt5_symbol,

            current_price=current_price,

            bid=self._decimal(
                market["bid"]
            ),

            ask=self._decimal(
                market["ask"]
            ),

            spread=self._decimal(
                market["spread"]
            ),

            signal="no_trade",

            direction="neutral",

            setup_quality="poor",

            confidence=0.0,

            setup_status=setup_status,

            next_action=next_action,

            market_condition=(
                market_analysis.market_condition
            ),

            overall_bias=overall_bias,

            entry_price=Decimal("0"),

            entry_zone_low=Decimal("0"),

            entry_zone_high=Decimal("0"),

            stop_loss=Decimal("0"),

            take_profit_1=Decimal("0"),

            take_profit_2=Decimal("0"),

            risk_reward_1=Decimal("0"),

            risk_reward_2=Decimal("0"),

            invalidation_price=Decimal("0"),

            confirmations=[],

            warnings=final_warnings,

            reasons=final_reasons,

            bullish_score=float(
                market_analysis.bullish_score
            ),

            bearish_score=float(
                market_analysis.bearish_score
            ),

            active_fvg_count=evidence[
                "active_fvg_count"
            ],

            active_order_block_count=evidence[
                "active_order_block_count"
            ],

            liquidity_sweep_count=evidence[
                "liquidity_sweep_count"
            ],

            support_count=evidence[
                "support_count"
            ],

            resistance_count=evidence[
                "resistance_count"
            ],

            execution_zone_analysis=(
                execution_zone_analysis
                if execution_zone_analysis is not None
                else {}
            ),
        )

    # =========================================================
    # MAIN ANALYSIS
    # =========================================================

    def analyze(
        self,
        symbol: str,
        timeframe: str = "15m",
        limit: int = 500,
        strength: int = 2,
        lookback: int = 20,
        minimum_touches: int = 2,
    ) -> MT5TradeSetup:

        normalized_symbol = (
            symbol.strip().upper()
        )

        normalized_timeframe = (
            timeframe.strip().lower()
        )

        if not normalized_symbol:
            raise MT5TradeSetupError(
                "Trading symbol cannot be empty"
            )

        if normalized_timeframe not in (
            self.VALID_TIMEFRAMES
        ):
            raise MT5TradeSetupError(
                f"Unsupported timeframe: "
                f"{normalized_timeframe}"
            )

        if limit < 50:
            raise MT5TradeSetupError(
                "Candle limit must be at least 50"
            )

        if strength < 1:
            raise MT5TradeSetupError(
                "Swing strength must be at least 1"
            )

        if lookback < 1:
            raise MT5TradeSetupError(
                "Order-block lookback must be at least 1"
            )

        if minimum_touches < 1:
            raise MT5TradeSetupError(
                "Minimum support/resistance touches "
                "must be at least 1"
            )

        # =====================================================
        # ENSURE MT5 CONNECTION
        # =====================================================

        self._ensure_mt5_connection()

        # =====================================================
        # MARKET
        # =====================================================

        market = self._get_market(
            normalized_symbol
        )

        mt5_symbol = market[
            "mt5_symbol"
        ]

        price_digits = self._get_broker_price_digits(
            mt5_symbol
        )

        # =====================================================
        # MARKET PRICE VALIDATION
        # =====================================================

        bid = self._decimal(
            market["bid"]
        )

        ask = self._decimal(
            market["ask"]
        )

        spread = self._decimal(
            market["spread"]
        )

        if bid <= 0 or ask <= 0:
            raise MT5TradeSetupError(
                f"Invalid MT5 market price for "
                f"{normalized_symbol}: "
                f"bid={bid}, ask={ask}"
            )

        if ask < bid:
            raise MT5TradeSetupError(
                f"Invalid MT5 market data for "
                f"{normalized_symbol}: ask is below bid"
            )

        if spread < 0:
            raise MT5TradeSetupError(
                f"Invalid MT5 spread for "
                f"{normalized_symbol}: {spread}"
            )

        # =====================================================
        # CANDLES
        # =====================================================

        candles = self._load_candles(
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            limit=limit,
        )

        if len(candles) < 20:
            raise MT5TradeSetupError(
                f"Insufficient MT5 candle data for "
                f"{normalized_symbol} "
                f"{normalized_timeframe}"
            )

        current_price = ask

        # =====================================================
        # VOLATILITY
        # =====================================================

        volatility = (
            self._calculate_recent_volatility(
                candles
            )
        )

        if volatility <= 0:
            raise MT5TradeSetupError(
                f"Unable to establish positive recent "
                f"volatility for {normalized_symbol} "
                f"{normalized_timeframe}"
            )

        # =====================================================
        # AI ANALYSIS
        # =====================================================

        try:

            market_analysis = (
                mt5_ai_market_analysis_service.analyze(
                    symbol=normalized_symbol,
                    timeframe=normalized_timeframe,
                    limit=limit,
                    strength=strength,
                    lookback=lookback,
                    minimum_touches=minimum_touches,
                )
            )

            mtf_analysis = (
                mt5_multi_timeframe_service.analyze(
                    symbol=normalized_symbol,
                    primary_timeframe=(
                        normalized_timeframe
                    ),
                    limit=limit,
                    strength=strength,
                    lookback=lookback,
                    minimum_touches=minimum_touches,
                )
            )

        except Exception as exc:
            raise MT5TradeSetupError(
                f"Unable to perform MT5 AI analysis: "
                f"{exc}"
            ) from exc

        # =====================================================
        # RAW STRUCTURAL EVIDENCE
        # =====================================================

        fvgs = detect_fair_value_gaps(
            candles
        )

        order_blocks = detect_order_blocks(
            candles,
            lookback=lookback,
        )

        liquidity_sweeps = (
            detect_liquidity_sweeps(
                candles,
                strength=strength,
            )
        )

        support_resistance = (
            detect_support_resistance(
                candles,
                current_price=current_price,
                minimum_touches=minimum_touches,
            )
        )

        support_levels = [
            level
            for level in support_resistance
            if level.type == "support"
        ]

        resistance_levels = [
            level
            for level in support_resistance
            if level.type == "resistance"
        ]

        active_fvgs = [
            fvg
            for fvg in fvgs
            if not fvg.mitigated
        ]

        active_order_blocks = [
            block
            for block in order_blocks
            if not block.mitigated
        ]

        evidence = {
            "active_fvg_count": len(
                active_fvgs
            ),

            "active_order_block_count": len(
                active_order_blocks
            ),

            "liquidity_sweep_count": len(
                liquidity_sweeps
            ),

            "support_count": len(
                support_levels
            ),

            "resistance_count": len(
                resistance_levels
            ),
        }

        # =====================================================
        # OVERALL MTF BIAS
        #
        # Trade direction comes ONLY from MTF analysis.
        # =====================================================

        overall_bias = (
            str(
                mtf_analysis.overall_bias
            )
            .strip()
            .lower()
        )

        # =====================================================
        # NEUTRAL BIAS
        # =====================================================

        if overall_bias not in {
            "bullish",
            "bearish",
        }:

            neutral_zone_analysis = (
                self._build_neutral_execution_zone_analysis(
                    current_price=current_price,
                    candles=candles,
                    fvgs=active_fvgs,
                    order_blocks=active_order_blocks,
                    volatility=volatility,
                )
            )

            return self._build_no_trade_setup(
                symbol=normalized_symbol,

                timeframe=normalized_timeframe,

                mt5_symbol=mt5_symbol,

                market=market,

                market_analysis=market_analysis,

                overall_bias=overall_bias,

                reason=(
                    "Multi-timeframe analysis does not "
                    "provide a directional trading bias"
                ),

                evidence=evidence,

                execution_zone_analysis=(
                    neutral_zone_analysis
                ),

                setup_status="no_trade",

                next_action="wait_for_directional_bias",

                reasons=[
                    (
                        "Multi-timeframe analysis does not "
                        "provide a directional trading bias"
                    ),

                    (
                        "Long and short execution zones "
                        "were evaluated independently without "
                        "selecting either direction"
                    ),

                    (
                        "No executable trade setup is permitted "
                        "while the higher-level directional bias "
                        "remains neutral"
                    ),
                ],

                warnings=[
                    (
                        "Multi-timeframe analysis does not "
                        "provide a directional trading bias"
                    ),
                ],
            )

        # =====================================================
        # TRADE DIRECTION
        # =====================================================

        direction = (
            "long"
            if overall_bias == "bullish"
            else "short"
        )

        evidence_direction = (
            self._market_direction_for_trade(
                direction
            )
        )

        # =====================================================
        # EXECUTION ZONE
        # =====================================================

        (
            zone_low,
            zone_high,
            zone_sources,
            execution_zone_analysis,
        ) = self._select_execution_zone(
            current_price=current_price,

            fvgs=active_fvgs,

            order_blocks=active_order_blocks,

            trade_direction=direction,

            candle_count=len(candles),

            volatility=volatility,
        )

        execution_zone_analysis[
            "price_digits"
        ] = price_digits

        execution_zone_analysis[
            "broker_price_precision"
        ] = f"{price_digits} decimal places"

        # =====================================================
        # NO VALID EXECUTION ZONE
        # =====================================================

        if (
            zone_low <= 0
            or zone_high <= 0
            or zone_high <= zone_low
        ):

            waiting_status = (
                execution_zone_analysis.get(
                    "waiting_status"
                )
            )

            waiting_reason = (
                execution_zone_analysis.get(
                    "waiting_reason"
                )
            )

            if (
                waiting_status
                == "waiting_for_price_to_reach_zone"
            ):

                reason = (
                    waiting_reason
                    or
                    "A recent directional execution zone "
                    "exists, but current price has not reached "
                    "the permitted execution area"
                )

                return self._build_no_trade_setup(
                    symbol=normalized_symbol,

                    timeframe=normalized_timeframe,

                    mt5_symbol=mt5_symbol,

                    market=market,

                    market_analysis=market_analysis,

                    overall_bias=overall_bias,

                    reason=reason,

                    evidence=evidence,

                    execution_zone_analysis=(
                        execution_zone_analysis
                    ),

                    setup_status=(
                        "waiting_for_entry_zone"
                    ),

                    next_action=(
                        "wait_for_price_to_reach_zone"
                    ),

                    reasons=[
                        reason,

                        (
                            f"MTF bias is "
                            f"{overall_bias}"
                        ),

                        (
                            "The execution engine is waiting "
                            "for price to reach a validated "
                            "directional execution zone"
                        ),

                        (
                            "No trade is permitted until the "
                            "execution zone satisfies the "
                            "distance and width requirements"
                        ),
                    ],

                    warnings=[
                        reason,
                    ],
                )

            if (
                waiting_status
                == "waiting_for_new_execution_evidence"
            ):

                reason = (
                    waiting_reason
                    or
                    "Directional evidence exists, but no "
                    "recent execution zone is currently valid"
                )

                return self._build_no_trade_setup(
                    symbol=normalized_symbol,

                    timeframe=normalized_timeframe,

                    mt5_symbol=mt5_symbol,

                    market=market,

                    market_analysis=market_analysis,

                    overall_bias=overall_bias,

                    reason=reason,

                    evidence=evidence,

                    execution_zone_analysis=(
                        execution_zone_analysis
                    ),

                    setup_status=(
                        "waiting_for_new_execution_evidence"
                    ),

                    next_action=(
                        "wait_for_new_execution_evidence"
                    ),

                    reasons=[
                        reason,

                        (
                            "The higher-level market bias "
                            "remains directional"
                        ),

                        (
                            "No recent FVG or order block "
                            "currently satisfies the execution "
                            "recency requirements"
                        ),

                        (
                            "No trade is permitted until "
                            "fresh execution evidence appears"
                        ),
                    ],

                    warnings=[
                        reason,
                    ],
                )

            reason = (
                waiting_reason
                or
                "No recent directional execution zone "
                "satisfies the current execution rules"
            )

            return self._build_no_trade_setup(
                symbol=normalized_symbol,

                timeframe=normalized_timeframe,

                mt5_symbol=mt5_symbol,

                market=market,

                market_analysis=market_analysis,

                overall_bias=overall_bias,

                reason=reason,

                evidence=evidence,

                execution_zone_analysis=(
                    execution_zone_analysis
                ),

                setup_status="no_trade",

                next_action=(
                    "wait_for_valid_execution_setup"
                ),
            )

        # =====================================================
        # ENTRY
        # =====================================================

        entry_price = (
            self._calculate_entry_price(
                current_price=current_price,

                direction=direction,

                zone_low=zone_low,

                zone_high=zone_high,
            )
        )

        entry_price = self._round_price(
            entry_price,
            digits=price_digits,
        )

        zone_low = self._round_price(
            zone_low,
            digits=price_digits,
        )

        zone_high = self._round_price(
            zone_high,
            digits=price_digits,
        )

        execution_zone_analysis[
            "entry_price_rounded"
        ] = entry_price

        if entry_price <= 0:

            return self._build_no_trade_setup(
                symbol=normalized_symbol,

                timeframe=normalized_timeframe,

                mt5_symbol=mt5_symbol,

                market=market,

                market_analysis=market_analysis,

                overall_bias=overall_bias,

                reason=(
                    "Unable to determine a valid execution "
                    "entry from the selected zone"
                ),

                evidence=evidence,

                execution_zone_analysis=(
                    execution_zone_analysis
                ),

                setup_status="no_trade",

                next_action=(
                    "wait_for_valid_execution_setup"
                ),
            )

        # =====================================================
        # ENTRY VALIDATION
        # =====================================================

        entry_distance_percent = (
            self._zone_distance_percent(
                current_price,
                zone_low,
                zone_high,
            )
        )

        execution_zone_analysis[
            "entry_price"
        ] = entry_price

        execution_zone_analysis[
            "entry_distance_percent"
        ] = entry_distance_percent

        if (
            entry_distance_percent
            > self.HARD_MAX_ENTRY_DISTANCE_PERCENT
        ):

            return self._build_no_trade_setup(
                symbol=normalized_symbol,

                timeframe=normalized_timeframe,

                mt5_symbol=mt5_symbol,

                market=market,

                market_analysis=market_analysis,

                overall_bias=overall_bias,

                reason=(
                    f"Entry distance is "
                    f"{entry_distance_percent:.2f}%, "
                    f"exceeding the "
                    f"{self.HARD_MAX_ENTRY_DISTANCE_PERCENT}% "
                    f"execution limit"
                ),

                evidence=evidence,

                execution_zone_analysis=(
                    execution_zone_analysis
                ),

                setup_status=(
                    "waiting_for_entry_zone"
                ),

                next_action=(
                    "wait_for_price_to_reach_zone"
                ),
            )

        # =====================================================
        # STOP LOSS
        # =====================================================

        stop_loss = (
            self._calculate_stop_loss(
                direction=direction,

                entry_price=entry_price,

                zone_low=zone_low,

                zone_high=zone_high,

                support_levels=support_levels,

                resistance_levels=resistance_levels,
            )
        )

        stop_loss = self._round_price(
            stop_loss,
            digits=price_digits,
        )

        execution_zone_analysis[
            "stop_loss_rounded"
        ] = stop_loss

        if stop_loss <= 0:

            return self._build_no_trade_setup(
                symbol=normalized_symbol,

                timeframe=normalized_timeframe,

                mt5_symbol=mt5_symbol,

                market=market,

                market_analysis=market_analysis,

                overall_bias=overall_bias,

                reason=(
                    "No valid structural stop-loss "
                    "could be established"
                ),

                evidence=evidence,

                execution_zone_analysis=(
                    execution_zone_analysis
                ),

                setup_status="no_trade",

                next_action=(
                    "wait_for_valid_risk_structure"
                ),
            )

        # =====================================================
        # STOP DISTANCE
        # =====================================================

        stop_distance = abs(
            entry_price
            - stop_loss
        )

        stop_distance_percent = (
            stop_distance
            / entry_price
            * Decimal("100")
        )

        execution_zone_analysis[
            "stop_loss"
        ] = stop_loss

        execution_zone_analysis[
            "stop_distance"
        ] = stop_distance

        execution_zone_analysis[
            "stop_distance_percent"
        ] = stop_distance_percent

        if (
            stop_distance_percent
            > self.HARD_MAX_STOP_DISTANCE_PERCENT
        ):

            return self._build_no_trade_setup(
                symbol=normalized_symbol,

                timeframe=normalized_timeframe,

                mt5_symbol=mt5_symbol,

                market=market,

                market_analysis=market_analysis,

                overall_bias=overall_bias,

                reason=(
                    f"Required stop distance is "
                    f"{stop_distance_percent:.2f}%, "
                    f"exceeding the "
                    f"{self.HARD_MAX_STOP_DISTANCE_PERCENT}% "
                    f"execution limit"
                ),

                evidence=evidence,

                execution_zone_analysis=(
                    execution_zone_analysis
                ),

                setup_status="no_trade",

                next_action=(
                    "wait_for_valid_risk_structure"
                ),
            )

        # =====================================================
        # TARGETS
        # =====================================================

        (
            take_profit_1,
            take_profit_2,
            target_analysis,
        ) = self._calculate_targets(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
        )

        take_profit_1 = self._round_price(
            take_profit_1,
            digits=price_digits,
        )

        take_profit_2 = self._round_price(
            take_profit_2,
            digits=price_digits,
        )

        execution_zone_analysis[
            "take_profit_1_rounded"
        ] = take_profit_1

        execution_zone_analysis[
            "take_profit_2_rounded"
        ] = take_profit_2

        execution_zone_analysis[
            "target_analysis"
        ] = target_analysis

        if (
            take_profit_1 <= 0
            or take_profit_2 <= 0
        ):

            return self._build_no_trade_setup(
                symbol=normalized_symbol,

                timeframe=normalized_timeframe,

                mt5_symbol=mt5_symbol,

                market=market,

                market_analysis=market_analysis,

                overall_bias=overall_bias,

                reason=(
                    target_analysis.get("rejection_reason")
                    or
                    "No realistic opposing structural targets provide the required 1.50R and 2.50R risk/reward levels"
                ),

                evidence=evidence,

                execution_zone_analysis=(
                    execution_zone_analysis
                ),

                setup_status="no_trade",

                next_action=(
                    "wait_for_valid_structural_targets"
                ),
            )

        # =====================================================
        # FINAL BROKER-ROUNDED GEOMETRY VALIDATION
        # =====================================================

        geometry_valid, geometry_error = (
            self._validate_final_price_geometry(
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit_1=take_profit_1,
                take_profit_2=take_profit_2,
            )
        )

        execution_zone_analysis[
            "final_geometry_valid"
        ] = geometry_valid

        execution_zone_analysis[
            "final_geometry_error"
        ] = geometry_error

        if not geometry_valid:
            return self._build_no_trade_setup(
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
                mt5_symbol=mt5_symbol,
                market=market,
                market_analysis=market_analysis,
                overall_bias=overall_bias,
                reason=geometry_error or "Final broker-rounded trade geometry is invalid",
                evidence=evidence,
                execution_zone_analysis=execution_zone_analysis,
                setup_status="no_trade",
                next_action="wait_for_valid_price_geometry",
            )

        # =====================================================
        # RISK / REWARD
        # =====================================================

        risk_reward_1 = (
            self._calculate_risk_reward(
                direction=direction,

                entry_price=entry_price,

                stop_loss=stop_loss,

                take_profit=take_profit_1,
            )
        )

        risk_reward_2 = (
            self._calculate_risk_reward(
                direction=direction,

                entry_price=entry_price,

                stop_loss=stop_loss,

                take_profit=take_profit_2,
            )
        )

        execution_zone_analysis[
            "take_profit_1"
        ] = take_profit_1

        execution_zone_analysis[
            "take_profit_2"
        ] = take_profit_2

        execution_zone_analysis[
            "risk_reward_1"
        ] = risk_reward_1

        execution_zone_analysis[
            "risk_reward_2"
        ] = risk_reward_2

        if (
            risk_reward_1
            < self.MIN_RISK_REWARD_1
        ):

            return self._build_no_trade_setup(
                symbol=normalized_symbol,

                timeframe=normalized_timeframe,

                mt5_symbol=mt5_symbol,

                market=market,

                market_analysis=market_analysis,

                overall_bias=overall_bias,

                reason=(
                    f"Risk/reward at TP1 is "
                    f"{risk_reward_1:.2f}, "
                    f"below the required minimum of "
                    f"{self.MIN_RISK_REWARD_1}"
                ),

                evidence=evidence,

                execution_zone_analysis=(
                    execution_zone_analysis
                ),

                setup_status="no_trade",

                next_action=(
                    "wait_for_better_risk_reward"
                ),
            )

        if (
            risk_reward_2
            < self.MIN_RISK_REWARD_2
        ):

            return self._build_no_trade_setup(
                symbol=normalized_symbol,

                timeframe=normalized_timeframe,

                mt5_symbol=mt5_symbol,

                market=market,

                market_analysis=market_analysis,

                overall_bias=overall_bias,

                reason=(
                    f"Risk/reward at TP2 is "
                    f"{risk_reward_2:.2f}, "
                    f"below the required minimum of "
                    f"{self.MIN_RISK_REWARD_2}"
                ),

                evidence=evidence,

                execution_zone_analysis=(
                    execution_zone_analysis
                ),

                setup_status="no_trade",

                next_action=(
                    "wait_for_better_risk_reward"
                ),
            )

        # =====================================================
        # CONFIRMATIONS
        # =====================================================

        confirmations: list[str] = []

        if (
            "higher_timeframe_confirmation"
            in mtf_analysis.confirmations
        ):
            confirmations.append(
                "higher_timeframe_confirmation"
            )

        if (
            "execution_timeframe_confirmation"
            in mtf_analysis.confirmations
        ):
            confirmations.append(
                "execution_timeframe_confirmation"
            )

        if "fvg" in zone_sources:
            confirmations.append(
                (
                    "active_"
                    + evidence_direction
                    + "_fvg"
                )
            )

        if "order_block" in zone_sources:
            confirmations.append(
                (
                    "active_"
                    + evidence_direction
                    + "_order_block"
                )
            )

        # =====================================================
        # LIQUIDITY CONFIRMATION
        # =====================================================

        recent_liquidity = [
            sweep
            for sweep in liquidity_sweeps
            if (
                sweep.direction
                == evidence_direction
                and (
                    len(candles)
                    - 1
                    - getattr(
                        sweep,
                        "swing_index",
                        len(candles) - 1,
                    )
                )
                <= self.RECENT_LIQUIDITY_CANDLES
            )
        ]

        if recent_liquidity:
            confirmations.append(
                f"{direction}_liquidity_sweep"
            )

        # =====================================================
        # MULTI-TIMEFRAME ALIGNMENT
        # =====================================================

        if (
            mtf_analysis.alignment
            in {
                "bullish_strongly_aligned",
                "bullish_aligned",
                "bearish_strongly_aligned",
                "bearish_aligned",
            }
        ):
            confirmations.append(
                "multi_timeframe_alignment"
            )

        # =====================================================
        # WARNINGS
        # =====================================================

        warnings = list(
            mtf_analysis.warnings
        )

        # =====================================================
        # CONFIDENCE / QUALITY
        # =====================================================

        confidence = float(
            mtf_analysis.confidence
        )

        if (
            confidence >= 80
            and len(confirmations) >= 4
            and risk_reward_1
            >= self.MIN_RISK_REWARD_1
            and risk_reward_2
            >= self.MIN_RISK_REWARD_2
            and stop_distance_percent
            <= Decimal("1.00")
        ):

            setup_quality = "high"

        elif (
            confidence >= 65
            and len(confirmations) >= 2
            and risk_reward_1
            >= self.MIN_RISK_REWARD_1
        ):

            setup_quality = "good"

        elif (
            confidence >= 50
            and len(confirmations) >= 1
            and risk_reward_1
            >= self.MIN_RISK_REWARD_1
        ):

            setup_quality = "moderate"

        else:

            setup_quality = "poor"

        if setup_quality == "poor":

            return self._build_no_trade_setup(
                symbol=normalized_symbol,

                timeframe=normalized_timeframe,

                mt5_symbol=mt5_symbol,

                market=market,

                market_analysis=market_analysis,

                overall_bias=overall_bias,

                reason=(
                    "Directional evidence exists, "
                    "but setup quality is insufficient "
                    "for execution"
                ),

                evidence=evidence,

                execution_zone_analysis=(
                    execution_zone_analysis
                ),

                setup_status="no_trade",

                next_action=(
                    "wait_for_higher_quality_setup"
                ),

                reasons=[
                    (
                        "Directional evidence exists, "
                        "but setup quality is insufficient "
                        "for execution"
                    ),

                    (
                        f"Multi-timeframe confidence is "
                        f"{confidence:.2f}"
                    ),

                    (
                        f"Only {len(confirmations)} "
                        f"execution confirmation(s) were "
                        f"established"
                    ),

                    (
                        "No trade is permitted until "
                        "the setup satisfies the execution "
                        "quality requirements"
                    ),
                ],

                warnings=warnings + [
                    (
                        "Setup quality is below the "
                        "minimum execution threshold"
                    ),
                ],
            )

        # =====================================================
        # REASONS
        # =====================================================

        reasons = [
            (
                "Recent volatility-adjusted "
                f"{direction} execution zone "
                "selected from "
                + " and ".join(
                    zone_sources
                )
            ),

            (
                f"Execution evidence direction is "
                f"{evidence_direction}"
            ),

            (
                f"Recent average candle range is "
                f"{volatility:.8f}"
            ),

            (
                "Structural stop-loss is within "
                "the permitted execution distance"
            ),

            (
                "Both take-profit targets are based "
                "on opposing structural levels"
            ),

            (
                "Risk/reward meets minimum requirements "
                f"at {risk_reward_1:.2f}R and "
                f"{risk_reward_2:.2f}R"
            ),
        ]

        if recent_liquidity:
            reasons.append(
                "Recent directional liquidity sweep "
                "confirms the setup"
            )

        if (
            mtf_analysis.higher_timeframe_bias
            == overall_bias
        ):
            reasons.append(
                "Higher-timeframe bias confirms "
                "the execution direction"
            )

        # =====================================================
        # FINAL RESULT
        #
        # Only a setup that survives ALL validation rules
        # reaches this point.
        # =====================================================

        return MT5TradeSetup(
            symbol=normalized_symbol,

            timeframe=normalized_timeframe,

            mt5_symbol=mt5_symbol,

            current_price=current_price,

            bid=bid,

            ask=ask,

            spread=spread,

            signal=direction,

            direction=direction,

            setup_quality=setup_quality,

            confidence=confidence,

            setup_status="ready",

            next_action="execute_if_risk_gate_allows",

            market_condition=(
                market_analysis.market_condition
            ),

            overall_bias=overall_bias,

            entry_price=entry_price,

            entry_zone_low=zone_low,

            entry_zone_high=zone_high,

            stop_loss=stop_loss,

            take_profit_1=take_profit_1,

            take_profit_2=take_profit_2,

            risk_reward_1=self._round_price(
                risk_reward_1,
                digits=2,
            ),

            risk_reward_2=self._round_price(
                risk_reward_2,
                digits=2,
            ),

            invalidation_price=stop_loss,

            confirmations=confirmations,

            warnings=warnings,

            reasons=reasons,

            bullish_score=float(
                market_analysis.bullish_score
            ),

            bearish_score=float(
                market_analysis.bearish_score
            ),

            active_fvg_count=evidence[
                "active_fvg_count"
            ],

            active_order_block_count=evidence[
                "active_order_block_count"
            ],

            liquidity_sweep_count=evidence[
                "liquidity_sweep_count"
            ],

            support_count=evidence[
                "support_count"
            ],

            resistance_count=evidence[
                "resistance_count"
            ],

            execution_zone_analysis=(
                execution_zone_analysis
            ),
        )

    # =========================================================
    # SERIALIZATION
    # =========================================================

    def serialize(
        self,
        setup: MT5TradeSetup,
    ) -> dict[str, Any]:

        return {
            "symbol": setup.symbol,

            "timeframe": setup.timeframe,

            "mt5_symbol": setup.mt5_symbol,

            "market": {
                "current_price":
                    setup.current_price,

                "bid":
                    setup.bid,

                "ask":
                    setup.ask,

                "spread":
                    setup.spread,
            },

            "signal":
                setup.signal,

            "direction":
                setup.direction,

            "setup_quality":
                setup.setup_quality,

            "confidence":
                setup.confidence,

            "setup_status":
                setup.setup_status,

            "next_action":
                setup.next_action,

            "market_condition":
                setup.market_condition,

            "overall_bias":
                setup.overall_bias,

            "entry_price":
                setup.entry_price,

            "entry_zone": {
                "low":
                    setup.entry_zone_low,

                "high":
                    setup.entry_zone_high,
            },

            "stop_loss":
                setup.stop_loss,

            "take_profit_1":
                setup.take_profit_1,

            "take_profit_2":
                setup.take_profit_2,

            "risk_reward_1":
                setup.risk_reward_1,

            "risk_reward_2":
                setup.risk_reward_2,

            "invalidation_price":
                setup.invalidation_price,

            "confirmations":
                setup.confirmations,

            "warnings":
                setup.warnings,

            "reasons":
                setup.reasons,

            "scores": {
                "bullish":
                    setup.bullish_score,

                "bearish":
                    setup.bearish_score,
            },

            "evidence": {
                "active_fvg_count":
                    setup.active_fvg_count,

                "active_order_block_count":
                    setup.active_order_block_count,

                "liquidity_sweep_count":
                    setup.liquidity_sweep_count,

                "support_count":
                    setup.support_count,

                "resistance_count":
                    setup.resistance_count,
            },

            "execution_zone_analysis":
                setup.execution_zone_analysis,
        }


# =============================================================
# SERVICE SINGLETON
# =============================================================

mt5_trade_setup_service = (
    MT5TradeSetupService()
)