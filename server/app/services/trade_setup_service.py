from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.services.ai_market_analysis_service import analyze_market
from app.services.candle_service import get_recent_candles
from app.services.fvg_service import detect_fair_value_gaps
from app.services.liquidity_service import detect_liquidity_sweeps
from app.services.multi_timeframe_service import analyze_multi_timeframe
from app.services.order_block_service import detect_order_blocks
from app.services.support_resistance_service import (
    detect_support_resistance,
    get_nearest_resistance,
    get_nearest_support,
)
from app.services.timeframe_service import aggregate_candles


@dataclass
class TradeSetup:
    symbol: str
    timeframe: str
    current_price: Decimal

    signal: str
    setup_quality: str
    confidence: int

    direction: str

    entry_price: Decimal | None
    entry_zone_low: Decimal | None
    entry_zone_high: Decimal | None

    stop_loss: Decimal | None
    take_profit_1: Decimal | None
    take_profit_2: Decimal | None

    risk_reward_1: Decimal | None
    risk_reward_2: Decimal | None

    invalidation_price: Decimal | None

    market_condition: str

    confirmations: list[str]
    warnings: list[str]
    reasons: list[str]

    bullish_score: int
    bearish_score: int


def _decimal(value: Decimal | float | int | None) -> Decimal | None:
    if value is None:
        return None

    return Decimal(str(value))


def _round_price(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None

    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _load_candles(
    db,
    symbol: str,
    timeframe: str,
    limit: int,
):
    if timeframe == "1m":
        return get_recent_candles(
            db=db,
            symbol=symbol,
            timeframe="1m",
            limit=limit,
        )

    return aggregate_candles(
        db=db,
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )


def _calculate_entry_zone(
    current_price: Decimal,
    direction: str,
    fair_value_gaps,
    order_blocks,
    nearest_support,
    nearest_resistance,
) -> tuple[Decimal, Decimal, Decimal] | None:
    zones: list[tuple[Decimal, Decimal]] = []

    if direction == "long":
        for gap in fair_value_gaps:
            if gap.direction != "bullish" or gap.mitigated:
                continue

            lower = _decimal(gap.lower_price)
            upper = _decimal(gap.upper_price)

            if lower is None or upper is None:
                continue

            if current_price >= lower:
                zones.append((lower, upper))

        for block in order_blocks:
            if block.direction != "bullish" or block.mitigated:
                continue

            lower = _decimal(block.lower_price)
            upper = _decimal(block.upper_price)

            if lower is None or upper is None:
                continue

            zones.append((lower, upper))

        if nearest_support is not None:
            support_price = _decimal(nearest_support.price)

            if support_price is not None:
                zones.append(
                    (
                        support_price,
                        current_price,
                    )
                )

    elif direction == "short":
        for gap in fair_value_gaps:
            if gap.direction != "bearish" or gap.mitigated:
                continue

            lower = _decimal(gap.lower_price)
            upper = _decimal(gap.upper_price)

            if lower is None or upper is None:
                continue

            if current_price <= upper:
                zones.append((lower, upper))

        for block in order_blocks:
            if block.direction != "bearish" or block.mitigated:
                continue

            lower = _decimal(block.lower_price)
            upper = _decimal(block.upper_price)

            if lower is None or upper is None:
                continue

            zones.append((lower, upper))

        if nearest_resistance is not None:
            resistance_price = _decimal(nearest_resistance.price)

            if resistance_price is not None:
                zones.append(
                    (
                        current_price,
                        resistance_price,
                    )
                )

    if not zones:
        return None

    if direction == "long":
        suitable_zones = [
            zone
            for zone in zones
            if zone[0] <= current_price
        ]

        if suitable_zones:
            selected = max(
                suitable_zones,
                key=lambda zone: zone[1],
            )
        else:
            selected = zones[0]

    else:
        suitable_zones = [
            zone
            for zone in zones
            if zone[1] >= current_price
        ]

        if suitable_zones:
            selected = min(
                suitable_zones,
                key=lambda zone: zone[0],
            )
        else:
            selected = zones[0]

    low = min(selected[0], selected[1])
    high = max(selected[0], selected[1])

    if direction == "long":
        entry_price = min(
            current_price,
            high,
        )
    else:
        entry_price = max(
            current_price,
            low,
        )

    return (
        _round_price(low),
        _round_price(high),
        _round_price(entry_price),
    )


def _calculate_stop_loss(
    direction: str,
    entry_price: Decimal,
    entry_zone_low: Decimal,
    entry_zone_high: Decimal,
    nearest_support,
    nearest_resistance,
) -> Decimal | None:

    if direction == "long":
        candidates: list[Decimal] = [
            entry_zone_low,
        ]

        if nearest_support is not None:
            support_price = _decimal(
                nearest_support.price
            )

            if support_price is not None:
                candidates.append(support_price)

        valid = [
            price
            for price in candidates
            if price < entry_price
        ]

        if not valid:
            return None

        base_stop = min(valid)

        distance = entry_price - base_stop

        if distance <= Decimal("0"):
            return None

        buffer = distance * Decimal("0.10")

        return _round_price(
            base_stop - buffer
        )

    if direction == "short":
        candidates = [
            entry_zone_high,
        ]

        if nearest_resistance is not None:
            resistance_price = _decimal(
                nearest_resistance.price
            )

            if resistance_price is not None:
                candidates.append(
                    resistance_price
                )

        valid = [
            price
            for price in candidates
            if price > entry_price
        ]

        if not valid:
            return None

        base_stop = max(valid)

        distance = base_stop - entry_price

        if distance <= Decimal("0"):
            return None

        buffer = distance * Decimal("0.10")

        return _round_price(
            base_stop + buffer
        )

    return None


def _calculate_take_profits(
    direction: str,
    entry_price: Decimal,
    stop_loss: Decimal,
    nearest_support,
    nearest_resistance,
) -> tuple[Decimal | None, Decimal | None]:

    risk = abs(entry_price - stop_loss)

    if risk <= Decimal("0"):
        return None, None

    if direction == "long":
        structural_target = None

        if nearest_resistance is not None:
            structural_target = _decimal(
                nearest_resistance.price
            )

        tp1_rr = entry_price + (
            risk * Decimal("1.50")
        )

        tp2_rr = entry_price + (
            risk * Decimal("2.50")
        )

        if (
            structural_target is not None
            and structural_target > entry_price
        ):
            tp1 = min(
                structural_target,
                tp1_rr,
            )
        else:
            tp1 = tp1_rr

        tp2 = max(
            tp2_rr,
            tp1 + risk,
        )

        return (
            _round_price(tp1),
            _round_price(tp2),
        )

    if direction == "short":
        structural_target = None

        if nearest_support is not None:
            structural_target = _decimal(
                nearest_support.price
            )

        tp1_rr = entry_price - (
            risk * Decimal("1.50")
        )

        tp2_rr = entry_price - (
            risk * Decimal("2.50")
        )

        if (
            structural_target is not None
            and structural_target < entry_price
        ):
            tp1 = max(
                structural_target,
                tp1_rr,
            )
        else:
            tp1 = tp1_rr

        tp2 = min(
            tp2_rr,
            tp1 - risk,
        )

        return (
            _round_price(tp1),
            _round_price(tp2),
        )

    return None, None


def _calculate_risk_reward(
    direction: str,
    entry_price: Decimal,
    stop_loss: Decimal,
    take_profit: Decimal,
) -> Decimal | None:

    risk = abs(
        entry_price - stop_loss
    )

    if risk <= Decimal("0"):
        return None

    reward = abs(
        take_profit - entry_price
    )

    if reward <= Decimal("0"):
        return None

    return (
        reward / risk
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _determine_setup_quality(
    confidence: int,
    confirmations: int,
    risk_reward_1: Decimal | None,
    risk_reward_2: Decimal | None,
    market_condition: str,
    warnings: list[str],
) -> str:

    if risk_reward_1 is None:
        return "invalid"

    if risk_reward_1 < Decimal("1.50"):
        return "invalid"

    if confirmations < 3:
        return "weak"

    if market_condition == "insufficient_data":
        return "invalid"

    if warnings:
        if confidence >= 70 and risk_reward_1 >= Decimal("2.00"):
            return "moderate"

        return "weak"

    if (
        confidence >= 80
        and confirmations >= 5
        and risk_reward_1 >= Decimal("2.00")
        and (
            risk_reward_2 is None
            or risk_reward_2 >= Decimal("2.50")
        )
    ):
        return "high"

    if (
        confidence >= 65
        and confirmations >= 4
        and risk_reward_1 >= Decimal("1.75")
    ):
        return "good"

    if (
        confidence >= 50
        and confirmations >= 3
    ):
        return "moderate"

    return "weak"


def _build_no_trade_setup(
    symbol: str,
    timeframe: str,
    current_price: Decimal,
    market_condition: str,
    bullish_score: int,
    bearish_score: int,
    confidence: int,
    reasons: list[str],
    warnings: list[str],
    confirmations: list[str],
) -> TradeSetup:

    return TradeSetup(
        symbol=symbol,
        timeframe=timeframe,
        current_price=current_price,
        signal="no_trade",
        setup_quality="invalid",
        confidence=min(confidence, 49),
        direction="neutral",
        entry_price=None,
        entry_zone_low=None,
        entry_zone_high=None,
        stop_loss=None,
        take_profit_1=None,
        take_profit_2=None,
        risk_reward_1=None,
        risk_reward_2=None,
        invalidation_price=None,
        market_condition=market_condition,
        confirmations=confirmations,
        warnings=warnings,
        reasons=reasons,
        bullish_score=bullish_score,
        bearish_score=bearish_score,
    )


def analyze_trade_setup(
    db,
    symbol: str,
    timeframe: str,
    current_price: Decimal,
    limit: int = 200,
) -> TradeSetup:

    normalized_symbol = symbol.strip().upper()
    normalized_timeframe = timeframe.strip().lower()

    candles = _load_candles(
        db=db,
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        limit=limit,
    )

    if len(candles) < 20:
        return _build_no_trade_setup(
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            current_price=current_price,
            market_condition="insufficient_data",
            bullish_score=0,
            bearish_score=0,
            confidence=0,
            reasons=[
                "Not enough confirmed candles are available for trade setup validation",
            ],
            warnings=[
                f"At least 20 {normalized_timeframe} candles are required",
            ],
            confirmations=[],
        )

    market_analysis = analyze_market(
        db=db,
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        current_price=current_price,
        limit=limit,
    )

    mtf_analysis = analyze_multi_timeframe(
        db=db,
        symbol=normalized_symbol,
        primary_timeframe=normalized_timeframe,
        current_price=current_price,
        limit=limit,
    )

    fair_value_gaps = detect_fair_value_gaps(
        candles=candles,
    )

    order_blocks = detect_order_blocks(
        candles=candles,
    )

    liquidity_sweeps = detect_liquidity_sweeps(
        candles=candles,
        strength=2,
    )

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

    confirmations: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []

    mtf_bias = mtf_analysis.overall_bias

    execution_bias = (
        mtf_analysis.execution_timeframe_bias
    )

    higher_bias = (
        mtf_analysis.higher_timeframe_bias
    )

    if mtf_bias not in {"bullish", "bearish"}:
        reasons.append(
            "Multi-timeframe analysis does not provide a confirmed directional bias"
        )

    if mtf_analysis.conflicts:
        warnings.extend(
            mtf_analysis.conflicts
        )

    if execution_bias != mtf_bias:
        warnings.append(
            "Execution timeframe does not agree with the overall multi-timeframe bias"
        )

    if (
        mtf_bias in {"bullish", "bearish"}
        and higher_bias == mtf_bias
    ):
        confirmations.append(
            "higher_timeframe_alignment"
        )

    if (
        mtf_bias in {"bullish", "bearish"}
        and execution_bias == mtf_bias
    ):
        confirmations.append(
            "execution_timeframe_alignment"
        )

    direction = (
        "long"
        if mtf_bias == "bullish"
        else "short"
        if mtf_bias == "bearish"
        else "neutral"
    )

    if direction == "neutral":
        return _build_no_trade_setup(
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            current_price=current_price,
            market_condition=mtf_analysis.analyses[
                next(
                    index
                    for index, item
                    in enumerate(mtf_analysis.analyses)
                    if item.timeframe == normalized_timeframe
                )
            ].market_condition,
            bullish_score=market_analysis.bullish_score,
            bearish_score=market_analysis.bearish_score,
            confidence=mtf_analysis.confidence,
            reasons=reasons,
            warnings=warnings,
            confirmations=confirmations,
        )

    if direction == "long":
        active_fvgs = [
            gap
            for gap in fair_value_gaps
            if gap.direction == "bullish"
            and not gap.mitigated
        ]

        active_blocks = [
            block
            for block in order_blocks
            if block.direction == "bullish"
            and not block.mitigated
        ]

        if active_fvgs:
            confirmations.append(
                "active_bullish_fvg"
            )

        if active_blocks:
            confirmations.append(
                "active_bullish_order_block"
            )

        bullish_sweeps = [
            sweep
            for sweep in liquidity_sweeps
            if str(
                getattr(
                    sweep,
                    "direction",
                    "",
                )
            ).lower()
            in {"bullish", "buy"}
        ]

        if bullish_sweeps:
            confirmations.append(
                "bullish_liquidity_sweep"
            )

        if nearest_support is not None:
            confirmations.append(
                "identified_support"
            )

        if nearest_resistance is not None:
            confirmations.append(
                "identified_resistance"
            )

    else:
        active_fvgs = [
            gap
            for gap in fair_value_gaps
            if gap.direction == "bearish"
            and not gap.mitigated
        ]

        active_blocks = [
            block
            for block in order_blocks
            if block.direction == "bearish"
            and not block.mitigated
        ]

        if active_fvgs:
            confirmations.append(
                "active_bearish_fvg"
            )

        if active_blocks:
            confirmations.append(
                "active_bearish_order_block"
            )

        bearish_sweeps = [
            sweep
            for sweep in liquidity_sweeps
            if str(
                getattr(
                    sweep,
                    "direction",
                    "",
                )
            ).lower()
            in {"bearish", "sell"}
        ]

        if bearish_sweeps:
            confirmations.append(
                "bearish_liquidity_sweep"
            )

        if nearest_support is not None:
            confirmations.append(
                "identified_support"
            )

        if nearest_resistance is not None:
            confirmations.append(
                "identified_resistance"
            )

    if len(confirmations) < 3:
        reasons.append(
            "The setup does not have at least three independent confirmations"
        )

    if direction == "long" and execution_bias != "bullish":
        warnings.append(
            "Long setup rejected because the execution timeframe is bearish"
        )

    if direction == "short" and execution_bias != "bearish":
        warnings.append(
            "Short setup rejected because the execution timeframe is bullish"
        )

    if (
        higher_bias in {"bullish", "bearish"}
        and higher_bias != mtf_bias
    ):
        warnings.append(
            "Higher timeframe direction conflicts with the proposed setup"
        )

    entry_zone = _calculate_entry_zone(
        current_price=current_price,
        direction=direction,
        fair_value_gaps=fair_value_gaps,
        order_blocks=order_blocks,
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
    )

    if entry_zone is None:
        reasons.append(
            "No valid structural entry zone was identified"
        )

        return _build_no_trade_setup(
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            current_price=current_price,
            market_condition=mtf_analysis.analyses[
                next(
                    index
                    for index, item
                    in enumerate(mtf_analysis.analyses)
                    if item.timeframe == normalized_timeframe
                )
            ].market_condition,
            bullish_score=market_analysis.bullish_score,
            bearish_score=market_analysis.bearish_score,
            confidence=mtf_analysis.confidence,
            reasons=reasons,
            warnings=warnings,
            confirmations=confirmations,
        )

    entry_zone_low, entry_zone_high, entry_price = (
        entry_zone
    )

    stop_loss = _calculate_stop_loss(
        direction=direction,
        entry_price=entry_price,
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
    )

    if stop_loss is None:
        reasons.append(
            "A valid structural stop-loss could not be calculated"
        )

        return _build_no_trade_setup(
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            current_price=current_price,
            market_condition=mtf_analysis.analyses[
                next(
                    index
                    for index, item
                    in enumerate(mtf_analysis.analyses)
                    if item.timeframe == normalized_timeframe
                )
            ].market_condition,
            bullish_score=market_analysis.bullish_score,
            bearish_score=market_analysis.bearish_score,
            confidence=mtf_analysis.confidence,
            reasons=reasons,
            warnings=warnings,
            confirmations=confirmations,
        )

    take_profit_1, take_profit_2 = (
        _calculate_take_profits(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            nearest_support=nearest_support,
            nearest_resistance=nearest_resistance,
        )
    )

    if take_profit_1 is None or take_profit_2 is None:
        reasons.append(
            "Valid take-profit targets could not be calculated"
        )

        return _build_no_trade_setup(
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            current_price=current_price,
            market_condition=mtf_analysis.analyses[
                next(
                    index
                    for index, item
                    in enumerate(mtf_analysis.analyses)
                    if item.timeframe == normalized_timeframe
                )
            ].market_condition,
            bullish_score=market_analysis.bullish_score,
            bearish_score=market_analysis.bearish_score,
            confidence=mtf_analysis.confidence,
            reasons=reasons,
            warnings=warnings,
            confirmations=confirmations,
        )

    risk_reward_1 = _calculate_risk_reward(
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit_1,
    )

    risk_reward_2 = _calculate_risk_reward(
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit_2,
    )

    if (
        risk_reward_1 is None
        or risk_reward_1 < Decimal("1.50")
    ):
        reasons.append(
            "Risk-to-reward at TP1 is below the minimum 1.50R requirement"
        )

    if (
        risk_reward_2 is not None
        and risk_reward_2 < Decimal("2.00")
    ):
        warnings.append(
            "TP2 does not provide at least 2.00R"
        )

    if not reasons:
        reasons.append(
            "Directional bias, multi-timeframe alignment, structural confirmation and risk parameters support the setup"
        )

    setup_quality = _determine_setup_quality(
        confidence=mtf_analysis.confidence,
        confirmations=len(confirmations),
        risk_reward_1=risk_reward_1,
        risk_reward_2=risk_reward_2,
        market_condition=(
            next(
                item.market_condition
                for item in mtf_analysis.analyses
                if item.timeframe == normalized_timeframe
            )
        ),
        warnings=warnings,
    )

    signal = (
        "long"
        if direction == "long"
        else "short"
    )

    if setup_quality == "invalid":
        signal = "no_trade"

    if signal == "no_trade":
        confidence = min(
            mtf_analysis.confidence,
            49,
        )
    else:
        confidence = min(
            mtf_analysis.confidence,
            95,
        )

    invalidation_price = stop_loss

    return TradeSetup(
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        current_price=current_price,
        signal=signal,
        setup_quality=setup_quality,
        confidence=confidence,
        direction=(
            direction
            if signal != "no_trade"
            else "neutral"
        ),
        entry_price=entry_price,
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        risk_reward_1=risk_reward_1,
        risk_reward_2=risk_reward_2,
        invalidation_price=invalidation_price,
        market_condition=(
            next(
                item.market_condition
                for item in mtf_analysis.analyses
                if item.timeframe == normalized_timeframe
            )
        ),
        confirmations=confirmations,
        warnings=warnings,
        reasons=reasons,
        bullish_score=market_analysis.bullish_score,
        bearish_score=market_analysis.bearish_score,
    )


def serialize_trade_setup(
    setup: TradeSetup,
) -> dict:

    return {
        "symbol": setup.symbol,
        "timeframe": setup.timeframe,
        "current_price": setup.current_price,
        "signal": setup.signal,
        "setup_quality": setup.setup_quality,
        "confidence": setup.confidence,
        "direction": setup.direction,
        "entry_price": setup.entry_price,
        "entry_zone": (
            {
                "low": setup.entry_zone_low,
                "high": setup.entry_zone_high,
            }
            if setup.entry_zone_low is not None
            and setup.entry_zone_high is not None
            else None
        ),
        "stop_loss": setup.stop_loss,
        "take_profit_1": setup.take_profit_1,
        "take_profit_2": setup.take_profit_2,
        "risk_reward_1": setup.risk_reward_1,
        "risk_reward_2": setup.risk_reward_2,
        "invalidation_price": setup.invalidation_price,
        "market_condition": setup.market_condition,
        "confirmations": setup.confirmations,
        "warnings": setup.warnings,
        "reasons": setup.reasons,
        "bullish_score": setup.bullish_score,
        "bearish_score": setup.bearish_score,
    }