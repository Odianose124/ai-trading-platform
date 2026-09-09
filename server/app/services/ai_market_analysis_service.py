from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.candle_service import get_recent_candles
from app.services.fvg_service import detect_fair_value_gaps
from app.services.liquidity_service import detect_liquidity_sweeps
from app.services.market_structure_service import determine_market_structure
from app.services.order_block_service import detect_order_blocks
from app.services.support_resistance_service import (
    detect_support_resistance,
    get_nearest_resistance,
    get_nearest_support,
)
from app.services.timeframe_service import aggregate_candles


@dataclass
class AnalysisComponent:
    name: str
    direction: str
    score: int
    reason: str


@dataclass
class MarketAnalysis:
    symbol: str
    timeframe: str
    current_price: Decimal
    bias: str
    confidence: int
    market_condition: str
    components: list[AnalysisComponent]
    bullish_score: int
    bearish_score: int


def _direction_from_structure(
    trend: str,
    structure: str,
) -> tuple[str, str]:
    normalized_trend = str(trend).strip().lower()
    normalized_structure = str(structure).strip().lower()

    if normalized_trend == "bullish" or normalized_structure == "bullish":
        return (
            "bullish",
            "Bullish market structure detected",
        )

    if normalized_trend == "bearish" or normalized_structure == "bearish":
        return (
            "bearish",
            "Bearish market structure detected",
        )

    return (
        "neutral",
        "Market structure is not decisively bullish or bearish",
    )


def _analyze_fvg(
    fair_value_gaps,
    current_price: Decimal,
) -> tuple[str, str]:
    active_gaps = [
        gap
        for gap in fair_value_gaps
        if not gap.mitigated
    ]

    if not active_gaps:
        return (
            "neutral",
            "No active fair value gap detected",
        )

    bullish = [
        gap
        for gap in active_gaps
        if gap.direction == "bullish"
        and gap.lower_price <= current_price <= gap.upper_price
    ]

    bearish = [
        gap
        for gap in active_gaps
        if gap.direction == "bearish"
        and gap.lower_price <= current_price <= gap.upper_price
    ]

    if bullish and not bearish:
        return (
            "bullish",
            "Price is currently interacting with an active bullish fair value gap",
        )

    if bearish and not bullish:
        return (
            "bearish",
            "Price is currently interacting with an active bearish fair value gap",
        )

    if bullish and bearish:
        return (
            "neutral",
            "Price is currently inside both bullish and bearish fair value gap zones",
        )

    return (
        "neutral",
        "Active fair value gaps exist but price is not currently inside a gap",
    )


def _analyze_liquidity(
    sweeps,
) -> tuple[str, str]:
    if not sweeps:
        return (
            "neutral",
            "No recent liquidity sweep detected",
        )

    latest = sweeps[-1]

    direction = str(
        getattr(latest, "direction", "")
    ).strip().lower()

    if direction in {"bullish", "buy"}:
        return (
            "bullish",
            "Recent sell-side liquidity sweep supports bullish reversal",
        )

    if direction in {"bearish", "sell"}:
        return (
            "bearish",
            "Recent buy-side liquidity sweep supports bearish reversal",
        )

    return (
        "neutral",
        "Liquidity sweep detected without a clear "
        "directional classification",
    )


def _analyze_order_blocks(
    order_blocks,
    current_price: Decimal,
) -> tuple[str, str]:
    """
    Analyze active order blocks using the actual OrderBlock fields:

        lower_price
        upper_price
        direction
        mitigated

    A bullish order block supports bullish bias.
    A bearish order block supports bearish bias.

    Price interaction with the block receives the strongest
    order-block confirmation.
    """

    active_blocks = [
        block
        for block in order_blocks
        if not block.mitigated
    ]

    if not active_blocks:
        return (
            "neutral",
            "No active order block detected",
        )

    bullish_blocks = [
        block
        for block in active_blocks
        if str(block.direction).strip().lower() == "bullish"
    ]

    bearish_blocks = [
        block
        for block in active_blocks
        if str(block.direction).strip().lower() == "bearish"
    ]

    bullish_interacting = [
        block
        for block in bullish_blocks
        if (
            Decimal(str(block.lower_price))
            <= current_price
            <= Decimal(str(block.upper_price))
        )
    ]

    bearish_interacting = [
        block
        for block in bearish_blocks
        if (
            Decimal(str(block.lower_price))
            <= current_price
            <= Decimal(str(block.upper_price))
        )
    ]

    # ---------------------------------------------------------
    # PRICE IS INTERACTING WITH ONLY A BULLISH ORDER BLOCK
    # ---------------------------------------------------------

    if bullish_interacting and not bearish_interacting:
        return (
            "bullish",
            "Price is currently interacting with an active bullish order block",
        )

    # ---------------------------------------------------------
    # PRICE IS INTERACTING WITH ONLY A BEARISH ORDER BLOCK
    # ---------------------------------------------------------

    if bearish_interacting and not bullish_interacting:
        return (
            "bearish",
            "Price is currently interacting with an active bearish order block",
        )

    # ---------------------------------------------------------
    # PRICE IS INTERACTING WITH BOTH DIRECTIONS
    # ---------------------------------------------------------

    if bullish_interacting and bearish_interacting:
        return (
            "neutral",
            "Price is currently interacting with both bullish and bearish order block zones",
        )

    # ---------------------------------------------------------
    # ONLY BULLISH ACTIVE BLOCKS EXIST
    # ---------------------------------------------------------

    if bullish_blocks and not bearish_blocks:
        return (
            "bullish",
            "Active bullish order block supports upward directional bias",
        )

    # ---------------------------------------------------------
    # ONLY BEARISH ACTIVE BLOCKS EXIST
    # ---------------------------------------------------------

    if bearish_blocks and not bullish_blocks:
        return (
            "bearish",
            "Active bearish order block supports downward directional bias",
        )

    # ---------------------------------------------------------
    # BOTH BULLISH AND BEARISH BLOCKS EXIST
    # ---------------------------------------------------------

    return (
        "neutral",
        "Both bullish and bearish order blocks are present, producing conflicting order-block signals",
    )


def _score_components(
    components: list[AnalysisComponent],
) -> tuple[int, int]:
    bullish_score = sum(
        component.score
        for component in components
        if component.direction == "bullish"
    )

    bearish_score = sum(
        component.score
        for component in components
        if component.direction == "bearish"
    )

    return bullish_score, bearish_score


def _determine_bias(
    bullish_score: int,
    bearish_score: int,
) -> tuple[str, int, str]:
    total_score = bullish_score + bearish_score

    if total_score == 0:
        return (
            "neutral",
            0,
            "insufficient_confirmation",
        )

    difference = abs(
        bullish_score - bearish_score
    )

    confidence = min(
        100,
        round(
            (difference / total_score) * 100
        ),
    )

    if bullish_score > bearish_score:
        bias = "long"

    elif bearish_score > bullish_score:
        bias = "short"

    else:
        bias = "neutral"

    if confidence >= 75:
        condition = "strong_trend"

    elif confidence >= 50:
        condition = "moderate_trend"

    elif confidence >= 25:
        condition = "mixed_market"

    else:
        condition = "range_or_uncertain"

    return (
        bias,
        confidence,
        condition,
    )


def _get_structure_value(
    structure_result: dict,
    key: str,
    default: str = "neutral",
) -> str:
    value = structure_result.get(
        key,
        default,
    )

    if value is None:
        return default

    return str(value)


def analyze_market(
    db,
    symbol: str,
    timeframe: str,
    current_price: Decimal,
    limit: int = 200,
) -> MarketAnalysis:
    normalized_symbol = symbol.strip().upper()
    normalized_timeframe = timeframe.strip().lower()

    # ---------------------------------------------------------
    # LOAD CANDLES
    # ---------------------------------------------------------

    if normalized_timeframe == "1m":
        candles = get_recent_candles(
            db=db,
            symbol=normalized_symbol,
            timeframe="1m",
            limit=limit,
        )

    else:
        candles = aggregate_candles(
            db=db,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            limit=limit,
        )

    # ---------------------------------------------------------
    # DATA VALIDATION
    # ---------------------------------------------------------

    if len(candles) < 10:
        return MarketAnalysis(
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            current_price=current_price,
            bias="neutral",
            confidence=0,
            market_condition="insufficient_data",
            components=[],
            bullish_score=0,
            bearish_score=0,
        )

    # ---------------------------------------------------------
    # 1. MARKET STRUCTURE
    # ---------------------------------------------------------

    structure_result = determine_market_structure(
        candles=candles,
        strength=2,
    )

    structure_trend = _get_structure_value(
        structure_result,
        "trend",
    )

    structure_state = _get_structure_value(
        structure_result,
        "structure",
    )

    structure_direction, structure_reason = (
        _direction_from_structure(
            trend=structure_trend,
            structure=structure_state,
        )
    )

    components = [
        AnalysisComponent(
            name="market_structure",
            direction=structure_direction,
            score=(
                30
                if structure_direction != "neutral"
                else 0
            ),
            reason=structure_reason,
        )
    ]

    # ---------------------------------------------------------
    # 2. LIQUIDITY
    # ---------------------------------------------------------

    sweeps = detect_liquidity_sweeps(
        candles=candles,
        strength=2,
    )

    liquidity_direction, liquidity_reason = (
        _analyze_liquidity(
            sweeps=sweeps,
        )
    )

    components.append(
        AnalysisComponent(
            name="liquidity",
            direction=liquidity_direction,
            score=(
                20
                if liquidity_direction != "neutral"
                else 0
            ),
            reason=liquidity_reason,
        )
    )

    # ---------------------------------------------------------
    # 3. FAIR VALUE GAPS
    # ---------------------------------------------------------

    fair_value_gaps = detect_fair_value_gaps(
        candles=candles,
    )

    fvg_direction, fvg_reason = _analyze_fvg(
        fair_value_gaps=fair_value_gaps,
        current_price=current_price,
    )

    components.append(
        AnalysisComponent(
            name="fair_value_gap",
            direction=fvg_direction,
            score=(
                15
                if fvg_direction != "neutral"
                else 0
            ),
            reason=fvg_reason,
        )
    )

    # ---------------------------------------------------------
    # 4. ORDER BLOCKS
    # ---------------------------------------------------------

    order_blocks = detect_order_blocks(
        candles=candles,
    )

    order_block_direction, order_block_reason = (
        _analyze_order_blocks(
            order_blocks=order_blocks,
            current_price=current_price,
        )
    )

    components.append(
        AnalysisComponent(
            name="order_block",
            direction=order_block_direction,
            score=(
                15
                if order_block_direction != "neutral"
                else 0
            ),
            reason=order_block_reason,
        )
    )

    # ---------------------------------------------------------
    # 5. SUPPORT & RESISTANCE
    # ---------------------------------------------------------

    levels = detect_support_resistance(
        candles=candles,
        current_price=current_price,
        minimum_touches=2,
    )

    nearest_support = get_nearest_support(
        levels=levels,
        current_price=current_price,
    )

    nearest_resistance = get_nearest_resistance(
        levels=levels,
        current_price=current_price,
    )

    sr_direction = "neutral"

    sr_reason = (
        "No immediate support/resistance confirmation"
    )

    if (
        nearest_support is not None
        and nearest_resistance is not None
    ):
        support_distance = abs(
            current_price
            - Decimal(
                str(nearest_support.price)
            )
        )

        resistance_distance = abs(
            Decimal(
                str(nearest_resistance.price)
            )
            - current_price
        )

        if support_distance < resistance_distance:
            sr_direction = "bullish"

            sr_reason = (
                "Price is closer to identified "
                "support than resistance"
            )

        elif resistance_distance < support_distance:
            sr_direction = "bearish"

            sr_reason = (
                "Price is closer to identified "
                "resistance than support"
            )

        else:
            sr_reason = (
                "Price is approximately balanced "
                "between support and resistance"
            )

    elif nearest_support is not None:
        sr_direction = "bullish"

        sr_reason = (
            "Nearest identified level is support"
        )

    elif nearest_resistance is not None:
        sr_direction = "bearish"

        sr_reason = (
            "Nearest identified level is resistance"
        )

    components.append(
        AnalysisComponent(
            name="support_resistance",
            direction=sr_direction,
            score=(
                20
                if sr_direction != "neutral"
                else 0
            ),
            reason=sr_reason,
        )
    )

    # ---------------------------------------------------------
    # FINAL CONFLUENCE SCORE
    # ---------------------------------------------------------

    bullish_score, bearish_score = (
        _score_components(
            components=components,
        )
    )

    bias, confidence, market_condition = (
        _determine_bias(
            bullish_score=bullish_score,
            bearish_score=bearish_score,
        )
    )

    # ---------------------------------------------------------
    # FINAL MARKET ANALYSIS
    # ---------------------------------------------------------

    return MarketAnalysis(
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        current_price=current_price,
        bias=bias,
        confidence=confidence,
        market_condition=market_condition,
        components=components,
        bullish_score=bullish_score,
        bearish_score=bearish_score,
    )


def serialize_market_analysis(
    analysis: MarketAnalysis,
) -> dict:
    return {
        "symbol": analysis.symbol,
        "timeframe": analysis.timeframe,
        "current_price": analysis.current_price,
        "bias": analysis.bias,
        "confidence": analysis.confidence,
        "market_condition": analysis.market_condition,
        "bullish_score": analysis.bullish_score,
        "bearish_score": analysis.bearish_score,
        "components": [
            {
                "name": component.name,
                "direction": component.direction,
                "score": component.score,
                "reason": component.reason,
            }
            for component in analysis.components
        ],
    }

