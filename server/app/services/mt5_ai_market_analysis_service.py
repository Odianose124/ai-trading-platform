from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.market_data_mt5.candle_adapter import mt5_candles_to_models
from app.market_data_mt5.candle_service import (
    MT5CandleDataError,
    mt5_candle_service,
)
from app.market_data_mt5.service import (
    MT5MarketDataError,
    mt5_market_data_service,
)
from app.services.mt5_fvg_service import (
    MT5FVGError,
    mt5_fvg_service,
)
from app.services.mt5_liquidity_service import (
    MT5LiquidityError,
    mt5_liquidity_service,
)
from app.services.mt5_market_structure_service import (
    MT5MarketStructureError,
    mt5_market_structure_service,
)
from app.services.mt5_order_block_service import (
    MT5OrderBlockError,
    mt5_order_block_service,
)
from app.services.mt5_support_resistance_service import (
    MT5SupportResistanceError,
    mt5_support_resistance_service,
)


@dataclass
class MT5AnalysisComponent:
    name: str
    weight: int
    bullish_score: float
    bearish_score: float
    confidence: float
    signal: str
    reason: str


@dataclass
class MT5MarketAnalysis:
    symbol: str
    timeframe: str
    mt5_symbol: str

    market: dict[str, Any]

    trend: str
    market_condition: str
    overall_bias: str
    confidence: float

    bullish_score: float
    bearish_score: float

    components: list[MT5AnalysisComponent]

    confirmations: list[str]
    warnings: list[str]
    reasons: list[str]

    market_structure: dict[str, Any]
    liquidity: dict[str, Any]
    fvg: dict[str, Any]
    order_blocks: dict[str, Any]
    support_resistance: dict[str, Any]


class MT5AIMarketAnalysisError(RuntimeError):
    """Raised when MT5 AI market analysis cannot be completed."""


class MT5AIMarketAnalysisService:

    STRUCTURE_WEIGHT = 30
    LIQUIDITY_WEIGHT = 20
    FVG_WEIGHT = 15
    ORDER_BLOCK_WEIGHT = 15
    SUPPORT_RESISTANCE_WEIGHT = 20

    VERY_NEAR_PERCENT = Decimal("0.15")
    NEAR_PERCENT = Decimal("0.35")
    RELEVANT_PERCENT = Decimal("0.75")
    MAX_RELEVANT_PERCENT = Decimal("1.50")

    def _decimal(self, value: Any) -> Decimal:
        try:
            return Decimal(str(value))
        except (TypeError, ValueError):
            return Decimal("0")

    def _clamp(
        self,
        value: float,
        minimum: float = 0.0,
        maximum: float = 100.0,
    ) -> float:
        return max(minimum, min(maximum, value))

    def _parse_datetime(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return None

    def _distance_percent(
        self,
        current_price: Decimal,
        target_price: Decimal,
    ) -> Decimal:
        if current_price <= 0:
            return Decimal("999")

        return (
            abs(target_price - current_price)
            / current_price
            * Decimal("100")
        )

    def _proximity_factor(
        self,
        distance_percent: Decimal,
    ) -> float:
        if distance_percent <= self.VERY_NEAR_PERCENT:
            return 1.00

        if distance_percent <= self.NEAR_PERCENT:
            return 0.85

        if distance_percent <= self.RELEVANT_PERCENT:
            return 0.65

        if distance_percent <= self.MAX_RELEVANT_PERCENT:
            return 0.35

        return 0.0

    def _recency_factor(
        self,
        event_time: Any,
        reference_time: Any,
    ) -> float:
        event_dt = self._parse_datetime(event_time)
        reference_dt = self._parse_datetime(reference_time)

        if event_dt is None or reference_dt is None:
            return 0.25

        age_seconds = max(
            0,
            (reference_dt - event_dt).total_seconds(),
        )

        age_minutes = age_seconds / 60

        if age_minutes <= 15:
            return 1.00

        if age_minutes <= 60:
            return 0.90

        if age_minutes <= 180:
            return 0.75

        if age_minutes <= 360:
            return 0.60

        if age_minutes <= 720:
            return 0.45

        if age_minutes <= 1440:
            return 0.30

        return 0.15

    def _direction_confidence(
        self,
        bullish_score: float,
        bearish_score: float,
    ) -> float:
        total = bullish_score + bearish_score

        if total <= 0:
            return 0.0

        return (
            abs(bullish_score - bearish_score)
            / total
            * 100
        )

    def _component_signal(
        self,
        bullish_score: float,
        bearish_score: float,
        minimum_directional_score: float = 8.0,
    ) -> str:
        if (
            bullish_score < minimum_directional_score
            and bearish_score < minimum_directional_score
        ):
            return "neutral"

        if bullish_score > bearish_score:
            return "bullish"

        if bearish_score > bullish_score:
            return "bearish"

        return "neutral"

    def _build_structure_component(
        self,
        market_structure: dict[str, Any],
    ) -> MT5AnalysisComponent:

        trend = str(
            market_structure.get("trend") or "neutral"
        ).lower()

        events = market_structure.get("structure", [])

        bullish_events = [
            event
            for event in events
            if str(event.get("direction", "")).lower() == "bullish"
        ]

        bearish_events = [
            event
            for event in events
            if str(event.get("direction", "")).lower() == "bearish"
        ]

        bullish_score = 0.0
        bearish_score = 0.0

        if trend == "bullish":
            bullish_score += 55.0

        elif trend == "bearish":
            bearish_score += 55.0

        recent_events = events[-8:]

        for event in recent_events:
            direction = str(
                event.get("direction", "")
            ).lower()

            event_type = str(
                event.get("type", "")
            ).upper()

            if event_type == "CHoCH":
                event_weight = 18.0
            else:
                event_weight = 12.0

            if direction == "bullish":
                bullish_score += event_weight

            elif direction == "bearish":
                bearish_score += event_weight

        bullish_score = self._clamp(bullish_score)
        bearish_score = self._clamp(bearish_score)

        signal = self._component_signal(
            bullish_score,
            bearish_score,
            minimum_directional_score=10,
        )

        confidence = self._direction_confidence(
            bullish_score,
            bearish_score,
        )

        if signal == "bullish":
            reason = (
                f"Market structure is bullish with "
                f"{len(bullish_events)} bullish structure event(s)"
            )

        elif signal == "bearish":
            reason = (
                f"Market structure is bearish with "
                f"{len(bearish_events)} bearish structure event(s)"
            )

        else:
            reason = (
                "Market structure does not currently provide "
                "a clear directional advantage"
            )

        return MT5AnalysisComponent(
            name="market_structure",
            weight=self.STRUCTURE_WEIGHT,
            bullish_score=round(bullish_score, 4),
            bearish_score=round(bearish_score, 4),
            confidence=round(confidence, 4),
            signal=signal,
            reason=reason,
        )

    def _build_fvg_component(
        self,
        fvg_data: dict[str, Any],
        current_price: Decimal,
        reference_time: Any,
    ) -> MT5AnalysisComponent:

        active_fvg = fvg_data.get("active_fvg", [])

        bullish_score = 0.0
        bearish_score = 0.0

        relevant_bullish = 0
        relevant_bearish = 0

        for gap in active_fvg:
            lower = self._decimal(
                gap.get("lower_price")
            )
            upper = self._decimal(
                gap.get("upper_price")
            )

            if lower <= 0 or upper <= 0:
                continue

            midpoint = (
                lower + upper
            ) / Decimal("2")

            distance = self._distance_percent(
                current_price,
                midpoint,
            )

            proximity = self._proximity_factor(distance)

            if proximity <= 0:
                continue

            recency = self._recency_factor(
                gap.get("created_time"),
                reference_time,
            )

            score = 35.0 * proximity * recency

            direction = str(
                gap.get("direction", "")
            ).lower()

            if direction == "bullish":
                bullish_score += score
                relevant_bullish += 1

            elif direction == "bearish":
                bearish_score += score
                relevant_bearish += 1

        bullish_score = self._clamp(bullish_score)
        bearish_score = self._clamp(bearish_score)

        signal = self._component_signal(
            bullish_score,
            bearish_score,
            minimum_directional_score=8,
        )

        confidence = self._direction_confidence(
            bullish_score,
            bearish_score,
        )

        if signal == "bullish":
            reason = (
                f"{relevant_bullish} relevant active bullish FVG(s)"
            )

        elif signal == "bearish":
            reason = (
                f"{relevant_bearish} relevant active bearish FVG(s)"
            )

        elif relevant_bullish or relevant_bearish:
            reason = (
                "Active FVG evidence is mixed and does not "
                "provide a clear directional advantage"
            )

        else:
            reason = (
                "No relevant active FVG provides a clear "
                "directional advantage"
            )

        return MT5AnalysisComponent(
            name="fvg",
            weight=self.FVG_WEIGHT,
            bullish_score=round(bullish_score, 4),
            bearish_score=round(bearish_score, 4),
            confidence=round(confidence, 4),
            signal=signal,
            reason=reason,
        )

    def _build_liquidity_component(
        self,
        liquidity_data: dict[str, Any],
        current_price: Decimal,
        reference_time: Any,
    ) -> MT5AnalysisComponent:

        sweeps = liquidity_data.get(
            "liquidity_sweeps",
            [],
        )

        recent_sweeps = sweeps[-8:]

        bullish_score = 0.0
        bearish_score = 0.0

        relevant_bullish = 0
        relevant_bearish = 0

        for sweep in recent_sweeps:
            liquidity_level = self._decimal(
                sweep.get("liquidity_level")
            )

            if liquidity_level <= 0:
                continue

            distance = self._distance_percent(
                current_price,
                liquidity_level,
            )

            proximity = self._proximity_factor(distance)

            if proximity <= 0:
                continue

            recency = self._recency_factor(
                sweep.get("time"),
                reference_time,
            )

            score = 45.0 * proximity * recency

            direction = str(
                sweep.get("direction", "")
            ).lower()

            if direction == "bullish":
                bullish_score += score
                relevant_bullish += 1

            elif direction == "bearish":
                bearish_score += score
                relevant_bearish += 1

        bullish_score = self._clamp(bullish_score)
        bearish_score = self._clamp(bearish_score)

        signal = self._component_signal(
            bullish_score,
            bearish_score,
            minimum_directional_score=8,
        )

        confidence = self._direction_confidence(
            bullish_score,
            bearish_score,
        )

        if signal == "bullish":
            reason = (
                f"{relevant_bullish} recent relevant bullish "
                f"liquidity sweep(s)"
            )

        elif signal == "bearish":
            reason = (
                f"{relevant_bearish} recent relevant bearish "
                f"liquidity sweep(s)"
            )

        elif relevant_bullish or relevant_bearish:
            reason = (
                "Liquidity evidence is mixed and does not "
                "provide a clear directional advantage"
            )

        else:
            reason = (
                "No recent relevant liquidity sweep provides "
                "a clear directional advantage"
            )

        return MT5AnalysisComponent(
            name="liquidity",
            weight=self.LIQUIDITY_WEIGHT,
            bullish_score=round(bullish_score, 4),
            bearish_score=round(bearish_score, 4),
            confidence=round(confidence, 4),
            signal=signal,
            reason=reason,
        )

    def _build_order_block_component(
        self,
        order_block_data: dict[str, Any],
        current_price: Decimal,
        reference_time: Any,
    ) -> MT5AnalysisComponent:

        active_blocks = order_block_data.get(
            "active_order_blocks",
            [],
        )

        bullish_score = 0.0
        bearish_score = 0.0

        relevant_bullish = 0
        relevant_bearish = 0

        for block in active_blocks:
            lower = self._decimal(
                block.get("lower_price")
            )
            upper = self._decimal(
                block.get("upper_price")
            )

            if lower <= 0 or upper <= 0:
                continue

            midpoint = (
                lower + upper
            ) / Decimal("2")

            distance = self._distance_percent(
                current_price,
                midpoint,
            )

            proximity = self._proximity_factor(distance)

            if proximity <= 0:
                continue

            recency = self._recency_factor(
                block.get("created_time"),
                reference_time,
            )

            score = 35.0 * proximity * recency

            direction = str(
                block.get("direction", "")
            ).lower()

            if direction == "bullish":
                bullish_score += score
                relevant_bullish += 1

            elif direction == "bearish":
                bearish_score += score
                relevant_bearish += 1

        bullish_score = self._clamp(bullish_score)
        bearish_score = self._clamp(bearish_score)

        signal = self._component_signal(
            bullish_score,
            bearish_score,
            minimum_directional_score=8,
        )

        confidence = self._direction_confidence(
            bullish_score,
            bearish_score,
        )

        if signal == "bullish":
            reason = (
                f"{relevant_bullish} relevant active bullish "
                f"order block(s)"
            )

        elif signal == "bearish":
            reason = (
                f"{relevant_bearish} relevant active bearish "
                f"order block(s)"
            )

        elif relevant_bullish or relevant_bearish:
            reason = (
                "Active order-block evidence is mixed and does "
                "not provide a clear directional advantage"
            )

        else:
            reason = (
                "No relevant active order block provides a "
                "clear directional advantage"
            )

        return MT5AnalysisComponent(
            name="order_blocks",
            weight=self.ORDER_BLOCK_WEIGHT,
            bullish_score=round(bullish_score, 4),
            bearish_score=round(bearish_score, 4),
            confidence=round(confidence, 4),
            signal=signal,
            reason=reason,
        )

    def _build_support_resistance_component(
        self,
        support_resistance_data: dict[str, Any],
        current_price: Decimal,
    ) -> MT5AnalysisComponent:

        active_support = support_resistance_data.get(
            "active_support",
            [],
        )

        active_resistance = support_resistance_data.get(
            "active_resistance",
            [],
        )

        nearest_support = support_resistance_data.get(
            "nearest_support"
        )

        nearest_resistance = support_resistance_data.get(
            "nearest_resistance"
        )

        bullish_score = 0.0
        bearish_score = 0.0

        context_parts: list[str] = []

        # ---------------------------------------------------------
        # IMPORTANT:
        # Support below price and resistance above price are NOT
        # automatically directional signals.
        #
        # They are market context and potential reaction areas.
        # ---------------------------------------------------------

        support_distance = None
        resistance_distance = None

        if nearest_support:
            support_price = self._decimal(
                nearest_support.get("price")
            )

            if support_price > 0:
                support_distance = self._distance_percent(
                    current_price,
                    support_price,
                )

                if support_price < current_price:
                    if (
                        support_distance
                        <= self.MAX_RELEVANT_PERCENT
                    ):
                        context_parts.append(
                            "relevant support below price"
                        )

        if nearest_resistance:
            resistance_price = self._decimal(
                nearest_resistance.get("price")
            )

            if resistance_price > 0:
                resistance_distance = self._distance_percent(
                    current_price,
                    resistance_price,
                )

                if resistance_price > current_price:
                    if (
                        resistance_distance
                        <= self.MAX_RELEVANT_PERCENT
                    ):
                        context_parts.append(
                            "relevant resistance above price"
                        )

        # ---------------------------------------------------------
        # Only create directional S/R evidence when the current
        # price is actually interacting with the level.
        #
        # A level merely being close is not enough.
        # ---------------------------------------------------------

        if nearest_support:
            support_price = self._decimal(
                nearest_support.get("price")
            )

            touches = int(
                nearest_support.get("touches", 0)
            )

            strength = float(
                nearest_support.get("strength", 0)
            )

            if (
                support_price > 0
                and support_price < current_price
                and support_distance is not None
                and support_distance <= self.VERY_NEAR_PERCENT
            ):
                reaction_factor = min(
                    1.0,
                    0.50 + (touches * 0.10),
                )

                bullish_score += (
                    20.0
                    * reaction_factor
                    * (strength / 100.0)
                )

        if nearest_resistance:
            resistance_price = self._decimal(
                nearest_resistance.get("price")
            )

            touches = int(
                nearest_resistance.get("touches", 0)
            )

            strength = float(
                nearest_resistance.get("strength", 0)
            )

            if (
                resistance_price > current_price
                and resistance_distance is not None
                and resistance_distance <= self.VERY_NEAR_PERCENT
            ):
                reaction_factor = min(
                    1.0,
                    0.50 + (touches * 0.10),
                )

                bearish_score += (
                    20.0
                    * reaction_factor
                    * (strength / 100.0)
                )

        # ---------------------------------------------------------
        # If there is no actual reaction evidence, keep S/R
        # neutral. This prevents nearby resistance from falsely
        # becoming a bearish trading signal.
        # ---------------------------------------------------------

        bullish_score = self._clamp(bullish_score)
        bearish_score = self._clamp(bearish_score)

        signal = self._component_signal(
            bullish_score,
            bearish_score,
            minimum_directional_score=8,
        )

        confidence = self._direction_confidence(
            bullish_score,
            bearish_score,
        )

        if signal == "bullish":
            reason = (
                "Price is interacting with nearby support and "
                "support reaction provides bullish context"
            )

        elif signal == "bearish":
            reason = (
                "Price is interacting with nearby resistance and "
                "resistance reaction provides bearish context"
            )

        elif context_parts:
            reason = (
                "Support/resistance is providing market context "
                "without sufficient reaction evidence for a "
                "directional signal"
            )

        else:
            reason = (
                "No nearby support/resistance interaction provides "
                "a clear directional advantage"
            )

        return MT5AnalysisComponent(
            name="support_resistance",
            weight=self.SUPPORT_RESISTANCE_WEIGHT,
            bullish_score=round(bullish_score, 4),
            bearish_score=round(bearish_score, 4),
            confidence=round(confidence, 4),
            signal=signal,
            reason=reason,
        )

    def _calculate_weighted_scores(
        self,
        components: list[MT5AnalysisComponent],
    ) -> tuple[float, float]:

        bullish_total = 0.0
        bearish_total = 0.0
        active_weight = 0.0

        for component in components:

            if (
                component.bullish_score <= 0
                and component.bearish_score <= 0
            ):
                continue

            weight = float(component.weight)

            bullish_total += (
                component.bullish_score
                * weight
            )

            bearish_total += (
                component.bearish_score
                * weight
            )

            active_weight += weight

        if active_weight <= 0:
            return 0.0, 0.0

        bullish_score = bullish_total / active_weight
        bearish_score = bearish_total / active_weight

        return (
            round(self._clamp(bullish_score), 4),
            round(self._clamp(bearish_score), 4),
        )

    def _calculate_evidence_quality(
        self,
        components: list[MT5AnalysisComponent],
    ) -> float:

        active_components = [
            component
            for component in components
            if component.signal != "neutral"
        ]

        if not active_components:
            return 0.0

        total_weight = sum(
            component.weight
            for component in active_components
        )

        if total_weight <= 0:
            return 0.0

        weighted_confidence = sum(
            component.confidence
            * component.weight
            for component in active_components
        )

        return self._clamp(
            weighted_confidence
            / total_weight
        )

    def _calculate_component_agreement(
        self,
        components: list[MT5AnalysisComponent],
    ) -> tuple[float, float]:

        directional_components = [
            component
            for component in components
            if component.signal in {
                "bullish",
                "bearish",
            }
        ]

        if not directional_components:
            return 0.0, 0.0

        bullish_weight = sum(
            component.weight
            for component in directional_components
            if component.signal == "bullish"
        )

        bearish_weight = sum(
            component.weight
            for component in directional_components
            if component.signal == "bearish"
        )

        total_weight = (
            bullish_weight
            + bearish_weight
        )

        if total_weight <= 0:
            return 0.0, 0.0

        dominant_weight = max(
            bullish_weight,
            bearish_weight,
        )

        opposing_weight = min(
            bullish_weight,
            bearish_weight,
        )

        agreement = (
            dominant_weight
            / total_weight
            * 100
        )

        conflict_ratio = (
            opposing_weight
            / total_weight
        )

        return (
            self._clamp(agreement),
            self._clamp(
                conflict_ratio * 100
            ),
        )

    def _determine_bias(
        self,
        components: list[MT5AnalysisComponent],
    ) -> tuple[str, float, float, float]:

        bullish_score, bearish_score = (
            self._calculate_weighted_scores(
                components
            )
        )

        if (
            bullish_score <= 0
            and bearish_score <= 0
        ):
            return (
                "neutral",
                0.0,
                bullish_score,
                bearish_score,
            )

        score_total = (
            bullish_score
            + bearish_score
        )

        if score_total <= 0:
            return (
                "neutral",
                0.0,
                bullish_score,
                bearish_score,
            )

        score_difference = (
            abs(
                bullish_score
                - bearish_score
            )
            / score_total
            * 100
        )

        if bullish_score > bearish_score:
            bias = "bullish"

        elif bearish_score > bullish_score:
            bias = "bearish"

        else:
            bias = "neutral"

        evidence_quality = (
            self._calculate_evidence_quality(
                components
            )
        )

        agreement, conflict_ratio = (
            self._calculate_component_agreement(
                components
            )
        )

        # ---------------------------------------------------------
        # Confidence model:
        #
        # 40% directional strength
        # 30% evidence quality
        # 20% component agreement
        # 10% conflict-adjusted stability
        # ---------------------------------------------------------

        directional_strength = self._clamp(
            score_difference
        )

        conflict_stability = (
            100.0 - conflict_ratio
        )

        confidence = (
            directional_strength * 0.40
            + evidence_quality * 0.30
            + agreement * 0.20
            + conflict_stability * 0.10
        )

        # Moderate conflict should reduce confidence,
        # but should not destroy strong structural evidence.
        if conflict_ratio >= 60:
            confidence *= 0.75

        elif conflict_ratio >= 45:
            confidence *= 0.85

        elif conflict_ratio >= 30:
            confidence *= 0.93

        confidence = self._clamp(
            confidence,
            0.0,
            95.0,
        )

        # If directional scores are almost equal, the analysis
        # should become neutral rather than forcing a direction.
        if score_total > 0:
            directional_gap = (
                abs(
                    bullish_score
                    - bearish_score
                )
                / score_total
            )

            if directional_gap < 0.08:
                bias = "neutral"
                confidence = min(
                    confidence,
                    49.0,
                )

        return (
            bias,
            round(confidence, 4),
            bullish_score,
            bearish_score,
        )

    def _market_condition(
        self,
        bias: str,
        confidence: float,
        components: list[MT5AnalysisComponent],
    ) -> str:

        directional_components = [
            component
            for component in components
            if component.signal in {
                "bullish",
                "bearish",
            }
        ]

        bullish_count = sum(
            1
            for component in directional_components
            if component.signal == "bullish"
        )

        bearish_count = sum(
            1
            for component in directional_components
            if component.signal == "bearish"
        )

        if bias == "neutral":
            return "mixed_market"

        if confidence >= 75:
            if bias == "bullish":
                return "strong_bullish_market"

            return "strong_bearish_market"

        if confidence >= 55:
            if bias == "bullish":
                return "bullish_market"

            return "bearish_market"

        if (
            bullish_count > 0
            and bearish_count > 0
        ):
            return "mixed_market"

        if bias == "bullish":
            return "bullish_market"

        if bias == "bearish":
            return "bearish_market"

        return "range_or_uncertain"

    def _build_confirmations(
        self,
        components: list[MT5AnalysisComponent],
        overall_bias: str,
    ) -> list[str]:

        confirmations: list[str] = []

        for component in components:
            if component.signal != overall_bias:
                continue

            if component.name == "market_structure":
                confirmations.append(
                    "market_structure_confirmation"
                )

            elif component.name == "liquidity":
                confirmations.append(
                    "liquidity_confirmation"
                )

            elif component.name == "fvg":
                confirmations.append(
                    "active_fvg_confirmation"
                )

            elif component.name == "order_blocks":
                confirmations.append(
                    "order_block_confirmation"
                )

            elif component.name == "support_resistance":
                confirmations.append(
                    "support_resistance_reaction_confirmation"
                )

        return confirmations

    def _build_warnings(
        self,
        components: list[MT5AnalysisComponent],
        overall_bias: str,
        confidence: float,
        support_resistance_data: dict[str, Any],
    ) -> list[str]:

        warnings: list[str] = []

        opposing_components = [
            component.name
            for component in components
            if (
                component.signal in {
                    "bullish",
                    "bearish",
                }
                and component.signal != overall_bias
                and component.confidence >= 20
            )
        ]

        if opposing_components:
            warnings.append(
                "Directional conflict detected in: "
                + ", ".join(opposing_components)
            )

        nearest_resistance = (
            support_resistance_data.get(
                "nearest_resistance"
            )
        )

        if nearest_resistance:
            resistance_price = self._decimal(
                nearest_resistance.get("price")
            )

            if resistance_price > 0:
                warnings.append(
                    "Relevant resistance is overhead and may "
                    "limit upside until price breaks and accepts "
                    "above the level"
                )

        nearest_support = (
            support_resistance_data.get(
                "nearest_support"
            )
        )

        if nearest_support:
            support_price = self._decimal(
                nearest_support.get("price")
            )

            if support_price > 0:
                warnings.append(
                    "Relevant support is below price and may "
                    "provide downside reaction or invalidation context"
                )

        if confidence < 50:
            warnings.append(
                "Overall analysis confidence is below 50%"
            )

        elif confidence < 65:
            warnings.append(
                "Overall analysis confidence is moderate; "
                "additional confirmation is recommended"
            )

        return warnings

    def _build_reasons(
        self,
        components: list[MT5AnalysisComponent],
        overall_bias: str,
        confidence: float,
    ) -> list[str]:

        reasons: list[str] = []

        ordered_components = sorted(
            components,
            key=lambda component: (
                component.weight
                * component.confidence
            ),
            reverse=True,
        )

        for component in ordered_components:
            if component.signal == overall_bias:
                reasons.append(
                    component.reason
                )

        opposing = [
            component
            for component in components
            if (
                component.signal in {
                    "bullish",
                    "bearish",
                }
                and component.signal != overall_bias
            )
        ]

        if opposing:
            names = ", ".join(
                component.name
                for component in opposing
            )

            reasons.append(
                f"Opposing evidence is present in: {names}"
            )

        if overall_bias == "bullish":
            if confidence >= 75:
                reasons.append(
                    "Bullish evidence is strongly aligned across "
                    "the highest-weight market components"
                )
            elif confidence >= 55:
                reasons.append(
                    "Bullish evidence has a meaningful advantage, "
                    "but some conflicting evidence remains"
                )
            else:
                reasons.append(
                    "Bullish directional evidence exists but "
                    "requires additional confirmation"
                )

        elif overall_bias == "bearish":
            if confidence >= 75:
                reasons.append(
                    "Bearish evidence is strongly aligned across "
                    "the highest-weight market components"
                )
            elif confidence >= 55:
                reasons.append(
                    "Bearish evidence has a meaningful advantage, "
                    "but some conflicting evidence remains"
                )
            else:
                reasons.append(
                    "Bearish directional evidence exists but "
                    "requires additional confirmation"
                )

        else:
            reasons.append(
                "Directional evidence is insufficiently aligned "
                "for a reliable market bias"
            )

        return reasons

    def _latest_candle_time(
        self,
        candles: list[Any],
    ) -> Any:

        if not candles:
            return datetime.now(timezone.utc)

        return candles[-1].close_time

    def analyze(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
        strength: int = 2,
        lookback: int = 20,
        minimum_touches: int = 2,
    ) -> MT5MarketAnalysis:

        normalized_symbol = (
            symbol.strip().upper()
        )

        normalized_timeframe = (
            timeframe.strip().lower()
        )

        if not normalized_symbol:
            raise MT5AIMarketAnalysisError(
                "Trading symbol cannot be empty"
            )

        if not normalized_timeframe:
            raise MT5AIMarketAnalysisError(
                "Timeframe cannot be empty"
            )

        if limit < 10:
            raise MT5AIMarketAnalysisError(
                "Limit must be at least 10 candles"
            )

        if strength < 1:
            raise MT5AIMarketAnalysisError(
                "Strength must be at least 1"
            )

        if lookback < 1:
            raise MT5AIMarketAnalysisError(
                "Lookback must be at least 1"
            )

        if minimum_touches < 1:
            raise MT5AIMarketAnalysisError(
                "Minimum touches must be at least 1"
            )

        # ---------------------------------------------------------
        # Get current MT5 market price
        # ---------------------------------------------------------

        try:
            tick = mt5_market_data_service.get_tick(
                normalized_symbol
            )

        except MT5MarketDataError as exc:
            raise MT5AIMarketAnalysisError(
                str(exc)
            ) from exc

        current_price = self._decimal(
            tick["bid"]
        )

        # ---------------------------------------------------------
        # Load candles once for reference time
        # ---------------------------------------------------------

        try:
            raw_candles = (
                mt5_candle_service.get_candles(
                    symbol=normalized_symbol,
                    timeframe=normalized_timeframe,
                    limit=limit,
                )
            )

            candles = mt5_candles_to_models(
                raw_candles
            )

        except MT5CandleDataError as exc:
            raise MT5AIMarketAnalysisError(
                str(exc)
            ) from exc

        if len(candles) < 10:
            raise MT5AIMarketAnalysisError(
                "Insufficient MT5 candle data for AI analysis"
            )

        reference_time = self._latest_candle_time(
            candles
        )

        mt5_symbol = raw_candles[0]["mt5_symbol"]

        # ---------------------------------------------------------
        # Run individual MT5 analysis engines
        # ---------------------------------------------------------

        try:
            market_structure = (
                mt5_market_structure_service.analyze(
                    symbol=normalized_symbol,
                    timeframe=normalized_timeframe,
                    limit=limit,
                    strength=strength,
                )
            )

            liquidity = (
                mt5_liquidity_service.analyze(
                    symbol=normalized_symbol,
                    timeframe=normalized_timeframe,
                    limit=limit,
                    strength=strength,
                )
            )

            fvg = (
                mt5_fvg_service.analyze(
                    symbol=normalized_symbol,
                    timeframe=normalized_timeframe,
                    limit=limit,
                )
            )

            order_blocks = (
                mt5_order_block_service.analyze(
                    symbol=normalized_symbol,
                    timeframe=normalized_timeframe,
                    limit=limit,
                    lookback=lookback,
                )
            )

            support_resistance = (
                mt5_support_resistance_service.analyze(
                    symbol=normalized_symbol,
                    timeframe=normalized_timeframe,
                    limit=limit,
                    minimum_touches=minimum_touches,
                )
            )

        except (
            MT5MarketStructureError,
            MT5LiquidityError,
            MT5FVGError,
            MT5OrderBlockError,
            MT5SupportResistanceError,
        ) as exc:
            raise MT5AIMarketAnalysisError(
                str(exc)
            ) from exc

        # ---------------------------------------------------------
        # Build AI components
        # ---------------------------------------------------------

        structure_component = (
            self._build_structure_component(
                market_structure
            )
        )

        liquidity_component = (
            self._build_liquidity_component(
                liquidity,
                current_price,
                reference_time,
            )
        )

        fvg_component = (
            self._build_fvg_component(
                fvg,
                current_price,
                reference_time,
            )
        )

        order_block_component = (
            self._build_order_block_component(
                order_blocks,
                current_price,
                reference_time,
            )
        )

        support_resistance_component = (
            self._build_support_resistance_component(
                support_resistance,
                current_price,
            )
        )

        components = [
            structure_component,
            liquidity_component,
            fvg_component,
            order_block_component,
            support_resistance_component,
        ]

        # ---------------------------------------------------------
        # Determine final AI bias
        # ---------------------------------------------------------

        (
            overall_bias,
            confidence,
            bullish_score,
            bearish_score,
        ) = self._determine_bias(
            components
        )

        trend = str(
            market_structure.get("trend")
            or "neutral"
        ).lower()

        market_condition = (
            self._market_condition(
                bias=overall_bias,
                confidence=confidence,
                components=components,
            )
        )

        confirmations = (
            self._build_confirmations(
                components=components,
                overall_bias=overall_bias,
            )
        )

        warnings = (
            self._build_warnings(
                components=components,
                overall_bias=overall_bias,
                confidence=confidence,
                support_resistance_data=(
                    support_resistance
                ),
            )
        )

        reasons = (
            self._build_reasons(
                components=components,
                overall_bias=overall_bias,
                confidence=confidence,
            )
        )

        market = {
            "current_price": tick["bid"],
            "bid": tick["bid"],
            "ask": tick["ask"],
            "spread": tick["spread"],
        }

        return MT5MarketAnalysis(
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            mt5_symbol=mt5_symbol,
            market=market,
            trend=trend,
            market_condition=market_condition,
            overall_bias=overall_bias,
            confidence=confidence,
            bullish_score=bullish_score,
            bearish_score=bearish_score,
            components=components,
            confirmations=confirmations,
            warnings=warnings,
            reasons=reasons,
            market_structure=market_structure,
            liquidity=liquidity,
            fvg=fvg,
            order_blocks=order_blocks,
            support_resistance=support_resistance,
        )

    def serialize(
        self,
        analysis: MT5MarketAnalysis,
    ) -> dict[str, Any]:

        return {
            "symbol": analysis.symbol,
            "timeframe": analysis.timeframe,
            "mt5_symbol": analysis.mt5_symbol,
            "market": analysis.market,
            "trend": analysis.trend,
            "market_condition": analysis.market_condition,
            "overall_bias": analysis.overall_bias,
            "confidence": analysis.confidence,
            "scores": {
                "bullish": analysis.bullish_score,
                "bearish": analysis.bearish_score,
            },
            "components": [
                {
                    "name": component.name,
                    "weight": component.weight,
                    "bullish_score": component.bullish_score,
                    "bearish_score": component.bearish_score,
                    "confidence": component.confidence,
                    "signal": component.signal,
                    "reason": component.reason,
                }
                for component in analysis.components
            ],
            "confirmations": analysis.confirmations,
            "warnings": analysis.warnings,
            "reasons": analysis.reasons,
            "market_structure": analysis.market_structure,
            "liquidity": analysis.liquidity,
            "fvg": analysis.fvg,
            "order_blocks": analysis.order_blocks,
            "support_resistance": analysis.support_resistance,
        }


mt5_ai_market_analysis_service = (
    MT5AIMarketAnalysisService()
)