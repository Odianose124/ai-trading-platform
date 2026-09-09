from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_UP


from app.services.ai_market_analysis_service import (
    analyze_market,
)


from app.services.candle_service import (
    get_recent_candles,
)


from app.services.fvg_service import (
    detect_fair_value_gaps,
)


from app.services.order_block_service import (
    detect_order_blocks,
)


from app.services.support_resistance_service import (
    detect_support_resistance,
    get_nearest_resistance,
    get_nearest_support,
)


from app.services.timeframe_service import (
    aggregate_candles,
)


from app.services.liquidity_service import (
    detect_liquidity_sweeps,
)


from app.services.market_structure_service import (
    determine_market_structure,
)


# ======================================================
# CONFIGURATION
# ======================================================

MINIMUM_CANDLES = 20
MINIMUM_CONFIRMATIONS = 4

MIN_RISK_REWARD_1 = Decimal("1.50")
MIN_RISK_REWARD_2 = Decimal("2.50")

STOP_BUFFER = Decimal("0.002")

DEFAULT_PRICE_DIGITS = 2

# Maximum distance between current price and the center
# of an institutional entry zone.
#
# This prevents the engine from selecting a historical
# zone that is technically valid but too far away.
MAX_ENTRY_ZONE_DISTANCE_PERCENT = Decimal("2.00")

# Maximum width of an institutional entry zone.
#
# A very wide zone is not treated as a precise execution
# area.
MAX_ENTRY_ZONE_WIDTH_PERCENT = Decimal("1.00")


# ======================================================
# TRADING SIGNAL DATA MODEL
# ======================================================

@dataclass
class TradingSignal:

    symbol: str

    timeframe: str

    current_price: Decimal

    # FINAL AI DECISION

    signal: str

    confidence: int

    signal_strength: str

    # ENTRY INFORMATION

    entry_price: Decimal | None

    entry_zone_low: Decimal | None

    entry_zone_high: Decimal | None

    # RISK MANAGEMENT

    stop_loss: Decimal | None

    take_profit_1: Decimal | None

    take_profit_2: Decimal | None

    risk_reward_1: Decimal | None

    risk_reward_2: Decimal | None

    invalidation_price: Decimal | None

    # MARKET CONTEXT

    market_condition: str

    # EXPLANATION

    confirmations: list[str]

    reasons: list[str]

    # SCORE ENGINE

    bullish_score: int

    bearish_score: int

    # INSTITUTIONAL METRICS

    liquidity_score: int = 0

    structure_score: int = 0

    order_block_score: int = 0

    fvg_score: int = 0

    institutional_score: int = 0


# ======================================================
# DECIMAL HELPERS
# ======================================================

def _decimal(value) -> Decimal:
    return Decimal(str(value))


def _round_price(
    value: Decimal,
    digits: int = DEFAULT_PRICE_DIGITS,
) -> Decimal:

    value = _decimal(value)

    if digits <= 0:

        return value.quantize(
            Decimal("1"),
            rounding=ROUND_DOWN,
        )

    quantum = Decimal(
        "0." + ("0" * digits)
    )

    return value.quantize(
        quantum,
        rounding=ROUND_DOWN,
    )


def _round_target_price(
    direction: str,
    value: Decimal,
    digits: int = DEFAULT_PRICE_DIGITS,
) -> Decimal:
    """
    Round take-profit prices in the direction that
    preserves the required risk/reward ratio.

    Long:
        TP rounds upward.

    Short:
        TP rounds downward.
    """

    value = _decimal(value)

    if digits <= 0:

        quantum = Decimal("1")

    else:

        quantum = Decimal(
            "0." + ("0" * digits)
        )

    if direction == "long":

        return value.quantize(
            quantum,
            rounding=ROUND_UP,
        )

    if direction == "short":

        return value.quantize(
            quantum,
            rounding=ROUND_DOWN,
        )

    return _round_price(
        value,
        digits,
    )


def _safe_int(
    value,
    default: int = 0,
) -> int:

    try:

        return int(value)

    except (
        TypeError,
        ValueError,
    ):

        return default


# ======================================================
# RISK REWARD CALCULATOR
# ======================================================

def _calculate_risk_reward(
    direction: str,
    entry: Decimal,
    stop_loss: Decimal,
    take_profit: Decimal,
):

    entry = _decimal(entry)

    stop_loss = _decimal(
        stop_loss
    )

    take_profit = _decimal(
        take_profit
    )

    if direction == "long":

        risk = (
            entry
            -
            stop_loss
        )

        reward = (
            take_profit
            -
            entry
        )

    elif direction == "short":

        risk = (
            stop_loss
            -
            entry
        )

        reward = (
            entry
            -
            take_profit
        )

    else:

        return None

    if risk <= Decimal("0"):

        return None

    if reward <= Decimal("0"):

        return None

    return (
        reward / risk
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_DOWN,
    )


# ======================================================
# FVG DETECTION
# ======================================================

def _get_active_fvgs(
    candles,
    current_price: Decimal,
):

    current_price = _decimal(
        current_price
    )

    try:

        gaps = detect_fair_value_gaps(
            candles
        )

    except Exception:

        return [], []

    # --------------------------------------------------
    # ONLY UNMITIGATED FVGs
    # --------------------------------------------------

    active = [
        gap
        for gap in gaps
        if not bool(
            getattr(
                gap,
                "mitigated",
                False,
            )
        )
    ]

    bullish = []

    bearish = []

    # --------------------------------------------------
    # DO NOT REQUIRE CURRENT PRICE TO BE INSIDE FVG
    #
    # The entry selector will decide whether the zone
    # is sufficiently close to current price.
    # --------------------------------------------------

    for gap in active:

        direction = str(
            getattr(
                gap,
                "direction",
                "",
            )
        ).lower()

        try:

            low = _decimal(
                gap.lower_price
            )

            high = _decimal(
                gap.upper_price
            )

        except (
            AttributeError,
            TypeError,
            ValueError,
        ):

            continue

        if low <= Decimal("0"):

            continue

        if high < low:

            continue

        if direction == "bullish":

            bullish.append(
                gap
            )

        elif direction == "bearish":

            bearish.append(
                gap
            )

    return (
        bullish,
        bearish,
    )


# ======================================================
# ORDER BLOCK DETECTION
# ======================================================

def _get_active_order_blocks(
    candles,
    current_price: Decimal,
):

    current_price = _decimal(
        current_price
    )

    try:

        blocks = detect_order_blocks(
            candles=candles,
        )

    except Exception:

        return [], []

    # --------------------------------------------------
    # ONLY UNMITIGATED ORDER BLOCKS
    # --------------------------------------------------

    active = [
        block
        for block in blocks
        if not bool(
            getattr(
                block,
                "mitigated",
                False,
            )
        )
    ]

    bullish = []

    bearish = []

    # --------------------------------------------------
    # DO NOT REQUIRE CURRENT PRICE TO BE INSIDE THE OB
    #
    # The entry selector performs proximity validation.
    # --------------------------------------------------

    for block in active:

        direction = str(
            getattr(
                block,
                "direction",
                "",
            )
        ).lower()

        try:

            low = _decimal(
                block.lower_price
            )

            high = _decimal(
                block.upper_price
            )

        except (
            AttributeError,
            TypeError,
            ValueError,
        ):

            continue

        if low <= Decimal("0"):

            continue

        if high < low:

            continue

        if direction == "bullish":

            bullish.append(
                block
            )

        elif direction == "bearish":

            bearish.append(
                block
            )

    return (
        bullish,
        bearish,
    )


# ======================================================
# LIQUIDITY ANALYSIS
# ======================================================

def _analyze_liquidity(
    candles,
    current_price: Decimal,
):

    score = 0

    confirmations = []

    reasons = []

    sweeps = []

    try:

        liquidity = detect_liquidity_sweeps(
            candles=candles,
            strength=2,
        )

        if not liquidity:

            return {
                "score": 0,
                "confirmations": [],
                "reasons": [],
                "sweeps": [],
            }

        current_price = _decimal(
            current_price
        )

        for item in liquidity:

            direction = str(
                getattr(
                    item,
                    "direction",
                    "",
                )
            ).lower()

            liquidity_level = _decimal(
                getattr(
                    item,
                    "liquidity_level",
                    current_price,
                )
            )

            sweep_price = _decimal(
                getattr(
                    item,
                    "sweep_price",
                    current_price,
                )
            )

            close_price = _decimal(
                getattr(
                    item,
                    "close_price",
                    current_price,
                )
            )

            if direction in {
                "buy",
                "long",
            }:

                direction = "bullish"

            elif direction in {
                "sell",
                "short",
            }:

                direction = "bearish"

            sweep = {
                "direction": direction,

                "liquidity_level":
                    liquidity_level,

                "sweep_price":
                    sweep_price,

                "close_price":
                    close_price,

                "time":
                    getattr(
                        item,
                        "time",
                        None,
                    ),

                "swing_time":
                    getattr(
                        item,
                        "swing_time",
                        None,
                    ),
            }

            sweeps.append(
                sweep
            )

            if direction == "bullish":

                score += 15

                confirmations.append(
                    "Bullish liquidity sweep detected"
                )

                reasons.append(
                    f"Bullish liquidity sweep near "
                    f"{liquidity_level}"
                )

            elif direction == "bearish":

                score += 15

                confirmations.append(
                    "Bearish liquidity sweep detected"
                )

                reasons.append(
                    f"Bearish liquidity sweep near "
                    f"{liquidity_level}"
                )

        confirmations = list(
            dict.fromkeys(
                confirmations
            )
        )

        reasons = list(
            dict.fromkeys(
                reasons
            )
        )

        score = min(
            score,
            25,
        )

        return {
            "score": score,
            "confirmations": confirmations,
            "reasons": reasons,
            "sweeps": sweeps,
        }

    except Exception:

        return {
            "score": 0,
            "confirmations": [],
            "reasons": [],
            "sweeps": [],
        }


# ======================================================
# MARKET STRUCTURE ANALYSIS
# ======================================================

def _analyze_structure(
    candles,
):

    score = 0

    confirmations = []

    reasons = []

    try:

        structure = determine_market_structure(
            candles=candles,
            strength=2,
        )

        trend = str(
            structure.get(
                "trend",
                "neutral",
            )
        ).lower()

        structure_type = str(
            structure.get(
                "structure",
                "range",
            )
        ).lower()

        events = structure.get(
            "events",
            [],
        )

        bullish_bos = False

        bearish_bos = False

        bullish_choch = False

        bearish_choch = False

        for event in events:

            event_direction = str(
                getattr(
                    event,
                    "direction",
                    "",
                )
            ).lower()

            event_type = str(
                getattr(
                    event,
                    "type",
                    "",
                )
            ).upper()

            if (
                event_type == "BOS"
                and
                event_direction == "bullish"
            ):

                bullish_bos = True

            elif (
                event_type == "BOS"
                and
                event_direction == "bearish"
            ):

                bearish_bos = True

            elif (
                event_type == "CHOCH"
                and
                event_direction == "bullish"
            ):

                bullish_choch = True

            elif (
                event_type == "CHOCH"
                and
                event_direction == "bearish"
            ):

                bearish_choch = True

        # --------------------------------------------------
        # TREND
        # --------------------------------------------------

        if trend == "bullish":

            score += 20

            confirmations.append(
                "Bullish market structure"
            )

            reasons.append(
                "Market structure is bullish"
            )

        elif trend == "bearish":

            score += 20

            confirmations.append(
                "Bearish market structure"
            )

            reasons.append(
                "Market structure is bearish"
            )

        # --------------------------------------------------
        # BOS
        # --------------------------------------------------

        if bullish_bos:

            score += 15

            confirmations.append(
                "Bullish BOS detected"
            )

            reasons.append(
                "Bullish break of structure detected"
            )

        if bearish_bos:

            score += 15

            confirmations.append(
                "Bearish BOS detected"
            )

            reasons.append(
                "Bearish break of structure detected"
            )

        # --------------------------------------------------
        # CHOCH
        # --------------------------------------------------

        if bullish_choch:

            score += 10

            confirmations.append(
                "Bullish CHoCH detected"
            )

            reasons.append(
                "Bullish change of character detected"
            )

        if bearish_choch:

            score += 10

            confirmations.append(
                "Bearish CHoCH detected"
            )

            reasons.append(
                "Bearish change of character detected"
            )

        # --------------------------------------------------
        # MARKET STRUCTURE QUALITY
        # --------------------------------------------------

        if structure_type == (
            "higher_highs_higher_lows"
        ):

            if trend == "bullish":

                score += 10

                confirmations.append(
                    "Higher highs and higher lows"
                )

                reasons.append(
                    "Price is forming higher highs and higher lows"
                )

        elif structure_type == (
            "lower_highs_lower_lows"
        ):

            if trend == "bearish":

                score += 10

                confirmations.append(
                    "Lower highs and lower lows"
                )

                reasons.append(
                    "Price is forming lower highs and lower lows"
                )

        score = min(
            score,
            55,
        )

        return {
            "score": score,

            "trend": trend,

            "structure": structure_type,

            "confirmations":
                list(
                    dict.fromkeys(
                        confirmations
                    )
                ),

            "reasons":
                list(
                    dict.fromkeys(
                        reasons
                    )
                ),

            "events": events,

            "swing_highs":
                structure.get(
                    "swing_highs",
                    [],
                ),

            "swing_lows":
                structure.get(
                    "swing_lows",
                    [],
                ),

            "bullish_bos":
                bullish_bos,

            "bearish_bos":
                bearish_bos,

            "bullish_choch":
                bullish_choch,

            "bearish_choch":
                bearish_choch,
        }

    except Exception:

        return {
            "score": 0,

            "trend": "neutral",

            "structure": "unavailable",

            "confirmations": [],

            "reasons": [],

            "events": [],

            "swing_highs": [],

            "swing_lows": [],

            "bullish_bos": False,

            "bearish_bos": False,

            "bullish_choch": False,

            "bearish_choch": False,
        }


# ======================================================
# SIGNAL STRENGTH ENGINE
# ======================================================

def _determine_signal_strength(
    confidence: int,
    confirmations: list[str],
    setup_available: bool = True,
):

    if not setup_available:

        return "insufficient"

    confirmation_count = len(
        confirmations
    )

    if (
        confidence >= 85
        and
        confirmation_count >= 5
    ):

        return "very_strong"

    if (
        confidence >= 70
        and
        confirmation_count >= 4
    ):

        return "strong"

    if (
        confidence >= 55
        and
        confirmation_count >= 3
    ):

        return "moderate"

    if confidence >= 40:

        return "weak"

    return "insufficient"


# ======================================================
# DIRECTIONAL LIQUIDITY CONFIRMATIONS
# ======================================================

def _get_directional_liquidity_confirmations(
    liquidity_analysis: dict,
    direction: str,
):

    evidence_direction = (
        "bullish"
        if direction == "long"
        else "bearish"
    )

    confirmations = []

    for sweep in liquidity_analysis.get(
        "sweeps",
        [],
    ):

        sweep_direction = str(
            sweep.get(
                "direction",
                "",
            )
        ).lower()

        if (
            sweep_direction
            != evidence_direction
        ):

            continue

        if evidence_direction == "bullish":

            confirmations.append(
                "Bullish liquidity sweep detected"
            )

        else:

            confirmations.append(
                "Bearish liquidity sweep detected"
            )

    return list(
        dict.fromkeys(
            confirmations
        )
    )


# ======================================================
# DIRECTIONAL STRUCTURE CONFIRMATIONS
# ======================================================

def _get_directional_structure_confirmations(
    structure_analysis: dict,
    direction: str,
):

    confirmations = []

    if direction == "long":

        if (
            structure_analysis.get(
                "trend"
            )
            == "bullish"
        ):

            confirmations.append(
                "Bullish market structure"
            )

        if structure_analysis.get(
            "bullish_bos",
            False,
        ):

            confirmations.append(
                "Bullish BOS detected"
            )

        if structure_analysis.get(
            "bullish_choch",
            False,
        ):

            confirmations.append(
                "Bullish CHoCH detected"
            )

        if (
            structure_analysis.get(
                "structure"
            )
            == "higher_highs_higher_lows"
        ):

            confirmations.append(
                "Higher highs and higher lows"
            )

    elif direction == "short":

        if (
            structure_analysis.get(
                "trend"
            )
            == "bearish"
        ):

            confirmations.append(
                "Bearish market structure"
            )

        if structure_analysis.get(
            "bearish_bos",
            False,
        ):

            confirmations.append(
                "Bearish BOS detected"
            )

        if structure_analysis.get(
            "bearish_choch",
            False,
        ):

            confirmations.append(
                "Bearish CHoCH detected"
            )

        if (
            structure_analysis.get(
                "structure"
            )
            == "lower_highs_lower_lows"
        ):

            confirmations.append(
                "Lower highs and lower lows"
            )

    return list(
        dict.fromkeys(
            confirmations
        )
    )


# ======================================================
# ENTRY ZONE DISTANCE
# ======================================================

def _zone_distance_percent(
    current_price: Decimal,
    zone_low: Decimal,
    zone_high: Decimal,
) -> Decimal:

    current_price = _decimal(
        current_price
    )

    zone_low = _decimal(
        zone_low
    )

    zone_high = _decimal(
        zone_high
    )

    if current_price <= Decimal("0"):

        return Decimal("999999")

    zone_center = (
        zone_low
        +
        zone_high
    ) / Decimal("2")

    return (
        abs(
            zone_center
            -
            current_price
        )
        /
        current_price
        *
        Decimal("100")
    )


# ======================================================
# ENTRY ZONE WIDTH
# ======================================================

def _zone_width_percent(
    zone_low: Decimal,
    zone_high: Decimal,
) -> Decimal:

    zone_low = _decimal(
        zone_low
    )

    zone_high = _decimal(
        zone_high
    )

    if zone_low <= Decimal("0"):

        return Decimal("999999")

    return (
        (
            zone_high
            -
            zone_low
        )
        /
        zone_low
        *
        Decimal("100")
    )


# ======================================================
# ENTRY ZONE SELECTOR
# ======================================================

def _select_entry_zone(
    direction: str,
    current_price: Decimal,
    bullish_fvgs,
    bearish_fvgs,
    bullish_blocks,
    bearish_blocks,
):

    current_price = _decimal(
        current_price
    )

    zones = []

    # ==================================================
    # LONG
    # ==================================================

    if direction == "long":

        for gap in bullish_fvgs:

            try:

                low = _decimal(
                    gap.lower_price
                )

                high = _decimal(
                    gap.upper_price
                )

            except (
                AttributeError,
                TypeError,
                ValueError,
            ):

                continue

            zones.append(
                {
                    "low": low,
                    "high": high,
                    "source": "FVG",
                }
            )

        for block in bullish_blocks:

            try:

                low = _decimal(
                    block.lower_price
                )

                high = _decimal(
                    block.upper_price
                )

            except (
                AttributeError,
                TypeError,
                ValueError,
            ):

                continue

            zones.append(
                {
                    "low": low,
                    "high": high,
                    "source": "Order Block",
                }
            )

    # ==================================================
    # SHORT
    # ==================================================

    elif direction == "short":

        for gap in bearish_fvgs:

            try:

                low = _decimal(
                    gap.lower_price
                )

                high = _decimal(
                    gap.upper_price
                )

            except (
                AttributeError,
                TypeError,
                ValueError,
            ):

                continue

            zones.append(
                {
                    "low": low,
                    "high": high,
                    "source": "FVG",
                }
            )

        for block in bearish_blocks:

            try:

                low = _decimal(
                    block.lower_price
                )

                high = _decimal(
                    block.upper_price
                )

            except (
                AttributeError,
                TypeError,
                ValueError,
            ):

                continue

            zones.append(
                {
                    "low": low,
                    "high": high,
                    "source": "Order Block",
                }
            )

    else:

        return (
            None,
            None,
            None,
            None,
        )

    # ==================================================
    # BASIC VALIDATION
    # ==================================================

    valid_zones = []

    for zone in zones:

        low = zone["low"]

        high = zone["high"]

        if low <= Decimal("0"):

            continue

        if high < low:

            continue

        width_percent = (
            _zone_width_percent(
                low,
                high,
            )
        )

        if (
            width_percent
            >
            MAX_ENTRY_ZONE_WIDTH_PERCENT
        ):

            continue

        distance_percent = (
            _zone_distance_percent(
                current_price,
                low,
                high,
            )
        )

        if (
            distance_percent
            >
            MAX_ENTRY_ZONE_DISTANCE_PERCENT
        ):

            continue

        valid_zones.append(
            zone
        )

    if not valid_zones:

        return (
            None,
            None,
            None,
            None,
        )

    # ==================================================
    # CURRENT PRICE INSIDE ZONE
    # ==================================================

    active = [
        zone
        for zone in valid_zones
        if (
            zone["low"]
            <= current_price
            <= zone["high"]
        )
    ]

    if active:

        # Prefer the narrowest genuine zone when price
        # is currently inside more than one zone.
        selected = min(
            active,
            key=lambda zone: (
                zone["high"]
                -
                zone["low"]
            ),
        )

    else:

        # Otherwise choose the closest genuine
        # unmitigated institutional zone.
        selected = min(
            valid_zones,
            key=lambda zone: (
                _zone_distance_percent(
                    current_price,
                    zone["low"],
                    zone["high"],
                ),
                zone["high"]
                -
                zone["low"],
            ),
        )

    low = selected["low"]

    high = selected["high"]

    entry = (
        low
        +
        high
    ) / Decimal("2")

    return (
        _round_price(
            entry
        ),

        _round_price(
            low
        ),

        _round_price(
            high
        ),

        selected["source"],
    )


# ======================================================
# INSTITUTIONAL CONFIDENCE ENGINE
# ======================================================

def _calculate_institutional_confidence(
    analysis,
    direction: str,
    liquidity_score: int,
    structure_score: int,
    fvg_score: int,
    order_block_score: int,
    confirmations: list[str],
):

    base_confidence = _safe_int(
        getattr(
            analysis,
            "confidence",
            0,
        )
    )

    bullish_score = _safe_int(
        getattr(
            analysis,
            "bullish_score",
            0,
        )
    )

    bearish_score = _safe_int(
        getattr(
            analysis,
            "bearish_score",
            0,
        )
    )

    if direction == "long":

        score_dominance = max(
            bullish_score
            -
            bearish_score,
            0,
        )

    else:

        score_dominance = max(
            bearish_score
            -
            bullish_score,
            0,
        )

    base_component = (
        Decimal(
            str(base_confidence)
        )
        *
        Decimal("0.45")
    )

    institutional_component = (
        Decimal(
            str(
                liquidity_score
                +
                structure_score
                +
                fvg_score
                +
                order_block_score
            )
        )
        *
        Decimal("0.45")
    )

    dominance_component = (
        min(
            Decimal(
                str(score_dominance)
            ),
            Decimal("20"),
        )
        *
        Decimal("0.50")
    )

    confirmation_component = (
        min(
            Decimal(
                str(
                    len(confirmations)
                )
            ),
            Decimal("5"),
        )
        *
        Decimal("2")
    )

    confidence = (
        base_component
        +
        institutional_component
        +
        dominance_component
        +
        confirmation_component
    )

    confidence = max(
        Decimal("0"),
        min(
            confidence,
            Decimal("95"),
        ),
    )

    return int(
        confidence.to_integral_value(
            rounding=ROUND_DOWN
        )
    )


# ======================================================
# AUTOMATIC SL / TP ENGINE
# ======================================================

def _calculate_trade_levels(
    direction: str,
    entry_price: Decimal,
    zone_low: Decimal,
    zone_high: Decimal,
    nearest_support,
    nearest_resistance,
):

    entry_price = _decimal(
        entry_price
    )

    zone_low = _decimal(
        zone_low
    )

    zone_high = _decimal(
        zone_high
    )

    # ==================================================
    # LONG
    # ==================================================

    if direction == "long":

        support = (
            _decimal(
                nearest_support.price
            )
            if nearest_support
            else zone_low
        )

        stop_reference = min(
            zone_low,
            support,
        )

        stop_loss = (
            stop_reference
            *
            (
                Decimal("1")
                -
                STOP_BUFFER
            )
        )

        risk_distance = (
            entry_price
            -
            stop_loss
        )

        if risk_distance <= Decimal("0"):

            return None

        minimum_tp1 = (
            entry_price
            +
            (
                risk_distance
                *
                MIN_RISK_REWARD_1
            )
        )

        minimum_tp2 = (
            entry_price
            +
            (
                risk_distance
                *
                MIN_RISK_REWARD_2
            )
        )

        take_profit_1 = minimum_tp1

        take_profit_2 = minimum_tp2

        if nearest_resistance:

            resistance = _decimal(
                nearest_resistance.price
            )

            if resistance > entry_price:

                take_profit_1 = max(
                    take_profit_1,
                    resistance,
                )

                take_profit_2 = max(
                    take_profit_2,
                    take_profit_1
                    +
                    risk_distance,
                )

        invalidation_price = stop_loss

    # ==================================================
    # SHORT
    # ==================================================

    elif direction == "short":

        resistance = (
            _decimal(
                nearest_resistance.price
            )
            if nearest_resistance
            else zone_high
        )

        stop_reference = max(
            zone_high,
            resistance,
        )

        stop_loss = (
            stop_reference
            *
            (
                Decimal("1")
                +
                STOP_BUFFER
            )
        )

        risk_distance = (
            stop_loss
            -
            entry_price
        )

        if risk_distance <= Decimal("0"):

            return None

        minimum_tp1 = (
            entry_price
            -
            (
                risk_distance
                *
                MIN_RISK_REWARD_1
            )
        )

        minimum_tp2 = (
            entry_price
            -
            (
                risk_distance
                *
                MIN_RISK_REWARD_2
            )
        )

        take_profit_1 = minimum_tp1

        take_profit_2 = minimum_tp2

        if nearest_support:

            support = _decimal(
                nearest_support.price
            )

            if support < entry_price:

                take_profit_1 = min(
                    take_profit_1,
                    support,
                )

                take_profit_2 = min(
                    take_profit_2,
                    take_profit_1
                    -
                    risk_distance,
                )

        invalidation_price = stop_loss

    else:

        return None

    return {
        "stop_loss":
            stop_loss,

        "take_profit_1":
            take_profit_1,

        "take_profit_2":
            take_profit_2,

        "invalidation_price":
            invalidation_price,
    }


# ======================================================
# FINAL PRICE VALIDATION
# ======================================================

def _validate_trade_prices(
    direction: str,
    entry: Decimal,
    stop_loss: Decimal,
    take_profit_1: Decimal,
    take_profit_2: Decimal,
):

    entry = _decimal(entry)

    stop_loss = _decimal(
        stop_loss
    )

    take_profit_1 = _decimal(
        take_profit_1
    )

    take_profit_2 = _decimal(
        take_profit_2
    )

    if direction == "long":

        return (
            stop_loss
            <
            entry
            <
            take_profit_1
            <
            take_profit_2
        )

    if direction == "short":

        return (
            take_profit_2
            <
            take_profit_1
            <
            entry
            <
            stop_loss
        )

    return False


# ======================================================
# MAIN AI TRADING SIGNAL GENERATOR
# ======================================================

def generate_trading_signal(
    db,
    symbol: str,
    timeframe: str,
    current_price: Decimal,
    limit: int = 200,
) -> TradingSignal:

    normalized_symbol = (
        symbol
        .strip()
        .upper()
    )

    normalized_timeframe = (
        timeframe
        .strip()
        .lower()
    )

    current_price = _decimal(
        current_price
    )

    # ==================================================
    # LOAD CANDLES
    # ==================================================

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

    # ==================================================
    # DATA VALIDATION
    # ==================================================

    if len(candles) < MINIMUM_CANDLES:

        return TradingSignal(
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            current_price=current_price,

            signal="no_trade",

            confidence=0,

            signal_strength="insufficient",

            entry_price=None,

            entry_zone_low=None,

            entry_zone_high=None,

            stop_loss=None,

            take_profit_1=None,

            take_profit_2=None,

            risk_reward_1=None,

            risk_reward_2=None,

            invalidation_price=None,

            market_condition="insufficient_data",

            confirmations=[],

            reasons=[
                "Minimum candle requirement not reached"
            ],

            bullish_score=0,

            bearish_score=0,

            liquidity_score=0,

            structure_score=0,

            order_block_score=0,

            fvg_score=0,

            institutional_score=0,
        )

    # ==================================================
    # AI MARKET ANALYSIS
    # ==================================================

    analysis = analyze_market(
        db=db,
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        current_price=current_price,
        limit=limit,
    )

    # ==================================================
    # INSTITUTIONAL ANALYSIS
    # ==================================================

    bullish_fvgs, bearish_fvgs = (
        _get_active_fvgs(
            candles,
            current_price,
        )
    )

    bullish_blocks, bearish_blocks = (
        _get_active_order_blocks(
            candles,
            current_price,
        )
    )

    liquidity_analysis = _analyze_liquidity(
        candles,
        current_price,
    )

    liquidity_score = _safe_int(
        liquidity_analysis.get(
            "score",
            0,
        )
    )

    structure_analysis = _analyze_structure(
        candles
    )

    structure_score = _safe_int(
        structure_analysis.get(
            "score",
            0,
        )
    )

    levels = detect_support_resistance(
        candles=candles,
        current_price=current_price,
        minimum_touches=2,
    )

    nearest_support = get_nearest_support(
        levels,
        current_price,
    )

    nearest_resistance = get_nearest_resistance(
        levels,
        current_price,
    )

    # ==================================================
    # AI SCORES
    # ==================================================

    bullish_score = _safe_int(
        getattr(
            analysis,
            "bullish_score",
            0,
        )
    )

    bearish_score = _safe_int(
        getattr(
            analysis,
            "bearish_score",
            0,
        )
    )

    # ==================================================
    # DETERMINE MARKET DIRECTION
    # ==================================================

    analysis_bias = str(
        getattr(
            analysis,
            "bias",
            "",
        )
    ).lower()

    if analysis_bias == "long":

        direction = "long"

    elif analysis_bias == "short":

        direction = "short"

    else:

        direction = "no_trade"

    # ==================================================
    # BASE METRICS
    # ==================================================

    fvg_score = 0

    order_block_score = 0

    confirmations = []

    reasons = []

    # ==================================================
    # LONG
    # ==================================================

    if direction == "long":

        if bullish_score > bearish_score:

            confirmations.append(
                "bullish_score_dominance"
            )

        if bullish_fvgs:

            fvg_score = 20

            confirmations.append(
                "bullish_fair_value_gap"
            )

        if bullish_blocks:

            order_block_score = 25

            confirmations.append(
                "bullish_order_block"
            )

        if nearest_support:

            confirmations.append(
                "support_zone"
            )

        confirmations.extend(
            _get_directional_liquidity_confirmations(
                liquidity_analysis,
                "long",
            )
        )

        confirmations.extend(
            _get_directional_structure_confirmations(
                structure_analysis,
                "long",
            )
        )

        reasons.append(
            "AI engine detected bullish institutional conditions"
        )

    # ==================================================
    # SHORT
    # ==================================================

    elif direction == "short":

        if bearish_score > bullish_score:

            confirmations.append(
                "bearish_score_dominance"
            )

        if bearish_fvgs:

            fvg_score = 20

            confirmations.append(
                "bearish_fair_value_gap"
            )

        if bearish_blocks:

            order_block_score = 25

            confirmations.append(
                "bearish_order_block"
            )

        if nearest_resistance:

            confirmations.append(
                "resistance_zone"
            )

        confirmations.extend(
            _get_directional_liquidity_confirmations(
                liquidity_analysis,
                "short",
            )
        )

        confirmations.extend(
            _get_directional_structure_confirmations(
                structure_analysis,
                "short",
            )
        )

        reasons.append(
            "AI engine detected bearish institutional conditions"
        )

    # ==================================================
    # REMOVE DUPLICATES
    # ==================================================

    confirmations = list(
        dict.fromkeys(
            confirmations
        )
    )

    reasons = list(
        dict.fromkeys(
            reasons
        )
    )

    # ==================================================
    # INSTITUTIONAL CONFIDENCE
    # ==================================================

    if direction in {
        "long",
        "short",
    }:

        confidence = (
            _calculate_institutional_confidence(
                analysis=analysis,
                direction=direction,
                liquidity_score=liquidity_score,
                structure_score=structure_score,
                fvg_score=fvg_score,
                order_block_score=order_block_score,
                confirmations=confirmations,
            )
        )

    else:

        confidence = _safe_int(
            getattr(
                analysis,
                "confidence",
                0,
            )
        )

        confidence = min(
            confidence,
            95,
        )

    institutional_score = (
        liquidity_score
        +
        structure_score
        +
        fvg_score
        +
        order_block_score
    )

    # ==================================================
    # NO DIRECTIONAL BIAS
    # ==================================================

    if direction not in {
        "long",
        "short",
    }:

        return TradingSignal(
            symbol=normalized_symbol,

            timeframe=normalized_timeframe,

            current_price=current_price,

            signal="no_trade",

            confidence=confidence,

            signal_strength="insufficient",

            entry_price=None,

            entry_zone_low=None,

            entry_zone_high=None,

            stop_loss=None,

            take_profit_1=None,

            take_profit_2=None,

            risk_reward_1=None,

            risk_reward_2=None,

            invalidation_price=None,

            market_condition=getattr(
                analysis,
                "market_condition",
                "unknown",
            ),

            confirmations=confirmations,

            reasons=reasons + [
                "AI market analysis does not provide a directional trade bias"
            ],

            bullish_score=bullish_score,

            bearish_score=bearish_score,

            liquidity_score=liquidity_score,

            structure_score=structure_score,

            order_block_score=order_block_score,

            fvg_score=fvg_score,

            institutional_score=institutional_score,
        )

    # ==================================================
    # DIRECTIONAL CONFIRMATION FILTER
    # ==================================================

    if len(confirmations) < MINIMUM_CONFIRMATIONS:

        return TradingSignal(
            symbol=normalized_symbol,

            timeframe=normalized_timeframe,

            current_price=current_price,

            signal="no_trade",

            confidence=confidence,

            signal_strength=_determine_signal_strength(
                confidence,
                confirmations,
                setup_available=False,
            ),

            entry_price=None,

            entry_zone_low=None,

            entry_zone_high=None,

            stop_loss=None,

            take_profit_1=None,

            take_profit_2=None,

            risk_reward_1=None,

            risk_reward_2=None,

            invalidation_price=None,

            market_condition=getattr(
                analysis,
                "market_condition",
                "unknown",
            ),

            confirmations=confirmations,

            reasons=reasons + [
                "Insufficient institutional confirmations"
            ],

            bullish_score=bullish_score,

            bearish_score=bearish_score,

            liquidity_score=liquidity_score,

            structure_score=structure_score,

            order_block_score=order_block_score,

            fvg_score=fvg_score,

            institutional_score=institutional_score,
        )

    # ==================================================
    # ENTRY ZONE
    # ==================================================

    (
        entry_price,
        zone_low,
        zone_high,
        zone_source,
    ) = _select_entry_zone(
        direction=direction,

        current_price=current_price,

        bullish_fvgs=bullish_fvgs,

        bearish_fvgs=bearish_fvgs,

        bullish_blocks=bullish_blocks,

        bearish_blocks=bearish_blocks,
    )

    # ==================================================
    # NO VALID ENTRY ZONE
    # ==================================================

    if entry_price is None:

        return TradingSignal(
            symbol=normalized_symbol,

            timeframe=normalized_timeframe,

            current_price=current_price,

            signal="no_trade",

            confidence=confidence,

            signal_strength="insufficient",

            entry_price=None,

            entry_zone_low=None,

            entry_zone_high=None,

            stop_loss=None,

            take_profit_1=None,

            take_profit_2=None,

            risk_reward_1=None,

            risk_reward_2=None,

            invalidation_price=None,

            market_condition=getattr(
                analysis,
                "market_condition",
                "unknown",
            ),

            confirmations=confirmations,

            reasons=reasons + [
                "No valid institutional entry zone within the permitted proximity"
            ],

            bullish_score=bullish_score,

            bearish_score=bearish_score,

            liquidity_score=liquidity_score,

            structure_score=structure_score,

            order_block_score=order_block_score,

            fvg_score=fvg_score,

            institutional_score=institutional_score,
        )

    confirmations.append(
        f"{zone_source} entry zone selected"
    )

    confirmations = list(
        dict.fromkeys(
            confirmations
        )
    )

    # ==================================================
    # AUTOMATIC STOP LOSS / TAKE PROFIT
    # ==================================================

    trade_levels = _calculate_trade_levels(
        direction=direction,

        entry_price=entry_price,

        zone_low=zone_low,

        zone_high=zone_high,

        nearest_support=nearest_support,

        nearest_resistance=nearest_resistance,
    )

    if trade_levels is None:

        return TradingSignal(
            symbol=normalized_symbol,

            timeframe=normalized_timeframe,

            current_price=current_price,

            signal="no_trade",

            confidence=confidence,

            signal_strength="insufficient",

            entry_price=entry_price,

            entry_zone_low=zone_low,

            entry_zone_high=zone_high,

            stop_loss=None,

            take_profit_1=None,

            take_profit_2=None,

            risk_reward_1=None,

            risk_reward_2=None,

            invalidation_price=None,

            market_condition=getattr(
                analysis,
                "market_condition",
                "unknown",
            ),

            confirmations=confirmations,

            reasons=reasons + [
                "Automatic SL/TP calculation failed"
            ],

            bullish_score=bullish_score,

            bearish_score=bearish_score,

            liquidity_score=liquidity_score,

            structure_score=structure_score,

            order_block_score=order_block_score,

            fvg_score=fvg_score,

            institutional_score=institutional_score,
        )

    # ==================================================
    # ROUND EXECUTABLE ENTRY / STOP
    # ==================================================

    entry_price = _round_price(
        entry_price
    )

    stop_loss = _round_price(
        trade_levels[
            "stop_loss"
        ]
    )

    invalidation_price = _round_price(
        trade_levels[
            "invalidation_price"
        ]
    )

    zone_low = _round_price(
        zone_low
    )

    zone_high = _round_price(
        zone_high
    )

    # ==================================================
    # REBUILD RISK FROM FINAL EXECUTABLE ENTRY / STOP
    # ==================================================

    if direction == "long":

        risk_distance = (
            entry_price
            -
            stop_loss
        )

    elif direction == "short":

        risk_distance = (
            stop_loss
            -
            entry_price
        )

    else:

        return TradingSignal(
            symbol=normalized_symbol,

            timeframe=normalized_timeframe,

            current_price=current_price,

            signal="no_trade",

            confidence=confidence,

            signal_strength="insufficient",

            entry_price=entry_price,

            entry_zone_low=zone_low,

            entry_zone_high=zone_high,

            stop_loss=stop_loss,

            take_profit_1=None,

            take_profit_2=None,

            risk_reward_1=None,

            risk_reward_2=None,

            invalidation_price=invalidation_price,

            market_condition=getattr(
                analysis,
                "market_condition",
                "unknown",
            ),

            confirmations=confirmations,

            reasons=reasons + [
                "Invalid trade direction"
            ],

            bullish_score=bullish_score,

            bearish_score=bearish_score,

            liquidity_score=liquidity_score,

            structure_score=structure_score,

            order_block_score=order_block_score,

            fvg_score=fvg_score,

            institutional_score=institutional_score,
        )

    if risk_distance <= Decimal("0"):

        return TradingSignal(
            symbol=normalized_symbol,

            timeframe=normalized_timeframe,

            current_price=current_price,

            signal="no_trade",

            confidence=confidence,

            signal_strength="insufficient",

            entry_price=entry_price,

            entry_zone_low=zone_low,

            entry_zone_high=zone_high,

            stop_loss=stop_loss,

            take_profit_1=None,

            take_profit_2=None,

            risk_reward_1=None,

            risk_reward_2=None,

            invalidation_price=invalidation_price,

            market_condition=getattr(
                analysis,
                "market_condition",
                "unknown",
            ),

            confirmations=confirmations,

            reasons=reasons + [
                "Invalid risk distance after price rounding"
            ],

            bullish_score=bullish_score,

            bearish_score=bearish_score,

            liquidity_score=liquidity_score,

            structure_score=structure_score,

            order_block_score=order_block_score,

            fvg_score=fvg_score,

            institutional_score=institutional_score,
        )

    # ==================================================
    # REBUILD MINIMUM TP LEVELS FROM FINAL RISK
    # ==================================================

    if direction == "long":

        minimum_tp1 = (
            entry_price
            +
            (
                risk_distance
                *
                MIN_RISK_REWARD_1
            )
        )

        minimum_tp2 = (
            entry_price
            +
            (
                risk_distance
                *
                MIN_RISK_REWARD_2
            )
        )

        calculated_tp1 = _decimal(
            trade_levels[
                "take_profit_1"
            ]
        )

        calculated_tp2 = _decimal(
            trade_levels[
                "take_profit_2"
            ]
        )

        take_profit_1 = max(
            calculated_tp1,
            minimum_tp1,
        )

        take_profit_2 = max(
            calculated_tp2,
            minimum_tp2,
        )

        if take_profit_2 <= take_profit_1:

            take_profit_2 = (
                take_profit_1
                +
                risk_distance
            )

    else:

        minimum_tp1 = (
            entry_price
            -
            (
                risk_distance
                *
                MIN_RISK_REWARD_1
            )
        )

        minimum_tp2 = (
            entry_price
            -
            (
                risk_distance
                *
                MIN_RISK_REWARD_2
            )
        )

        calculated_tp1 = _decimal(
            trade_levels[
                "take_profit_1"
            ]
        )

        calculated_tp2 = _decimal(
            trade_levels[
                "take_profit_2"
            ]
        )

        take_profit_1 = min(
            calculated_tp1,
            minimum_tp1,
        )

        take_profit_2 = min(
            calculated_tp2,
            minimum_tp2,
        )

        if take_profit_2 >= take_profit_1:

            take_profit_2 = (
                take_profit_1
                -
                risk_distance
            )

    # ==================================================
    # ROUND TP IN RR-PRESERVING DIRECTION
    # ==================================================

    take_profit_1 = _round_target_price(
        direction=direction,

        value=take_profit_1,
    )

    take_profit_2 = _round_target_price(
        direction=direction,

        value=take_profit_2,
    )

    # ==================================================
    # FINAL RR PROTECTION AFTER TP ROUNDING
    # ==================================================

    if direction == "long":

        minimum_tp1_rounded = (
            _round_target_price(
                direction="long",

                value=(
                    entry_price
                    +
                    (
                        risk_distance
                        *
                        MIN_RISK_REWARD_1
                    )
                ),
            )
        )

        minimum_tp2_rounded = (
            _round_target_price(
                direction="long",

                value=(
                    entry_price
                    +
                    (
                        risk_distance
                        *
                        MIN_RISK_REWARD_2
                    )
                ),
            )
        )

        take_profit_1 = max(
            take_profit_1,
            minimum_tp1_rounded,
        )

        take_profit_2 = max(
            take_profit_2,
            minimum_tp2_rounded,
        )

        if take_profit_2 <= take_profit_1:

            take_profit_2 = _round_target_price(
                direction="long",

                value=(
                    take_profit_1
                    +
                    risk_distance
                ),
            )

    else:

        minimum_tp1_rounded = (
            _round_target_price(
                direction="short",

                value=(
                    entry_price
                    -
                    (
                        risk_distance
                        *
                        MIN_RISK_REWARD_1
                    )
                ),
            )
        )

        minimum_tp2_rounded = (
            _round_target_price(
                direction="short",

                value=(
                    entry_price
                    -
                    (
                        risk_distance
                        *
                        MIN_RISK_REWARD_2
                    )
                ),
            )
        )

        take_profit_1 = min(
            take_profit_1,
            minimum_tp1_rounded,
        )

        take_profit_2 = min(
            take_profit_2,
            minimum_tp2_rounded,
        )

        if take_profit_2 >= take_profit_1:

            take_profit_2 = _round_target_price(
                direction="short",

                value=(
                    take_profit_1
                    -
                    risk_distance
                ),
            )

    # ==================================================
    # FINAL PRICE GEOMETRY
    # ==================================================

    if not _validate_trade_prices(
        direction=direction,

        entry=entry_price,

        stop_loss=stop_loss,

        take_profit_1=take_profit_1,

        take_profit_2=take_profit_2,
    ):

        return TradingSignal(
            symbol=normalized_symbol,

            timeframe=normalized_timeframe,

            current_price=current_price,

            signal="no_trade",

            confidence=confidence,

            signal_strength="insufficient",

            entry_price=entry_price,

            entry_zone_low=zone_low,

            entry_zone_high=zone_high,

            stop_loss=stop_loss,

            take_profit_1=take_profit_1,

            take_profit_2=take_profit_2,

            risk_reward_1=None,

            risk_reward_2=None,

            invalidation_price=invalidation_price,

            market_condition=getattr(
                analysis,
                "market_condition",
                "unknown",
            ),

            confirmations=confirmations,

            reasons=reasons + [
                "Invalid entry, stop loss or take profit geometry"
            ],

            bullish_score=bullish_score,

            bearish_score=bearish_score,

            liquidity_score=liquidity_score,

            structure_score=structure_score,

            order_block_score=order_block_score,

            fvg_score=fvg_score,

            institutional_score=institutional_score,
        )

    # ==================================================
    # FINAL RISK REWARD
    # ==================================================

    risk_reward_1 = _calculate_risk_reward(
        direction=direction,

        entry=entry_price,

        stop_loss=stop_loss,

        take_profit=take_profit_1,
    )

    risk_reward_2 = _calculate_risk_reward(
        direction=direction,

        entry=entry_price,

        stop_loss=stop_loss,

        take_profit=take_profit_2,
    )

    # ==================================================
    # RISK REWARD FILTER
    # ==================================================

    if (
        risk_reward_1 is None
        or
        risk_reward_2 is None
        or
        risk_reward_1 < MIN_RISK_REWARD_1
        or
        risk_reward_2 < MIN_RISK_REWARD_2
    ):

        return TradingSignal(
            symbol=normalized_symbol,

            timeframe=normalized_timeframe,

            current_price=current_price,

            signal="no_trade",

            confidence=confidence,

            signal_strength="insufficient",

            entry_price=entry_price,

            entry_zone_low=zone_low,

            entry_zone_high=zone_high,

            stop_loss=stop_loss,

            take_profit_1=take_profit_1,

            take_profit_2=take_profit_2,

            risk_reward_1=risk_reward_1,

            risk_reward_2=risk_reward_2,

            invalidation_price=invalidation_price,

            market_condition=getattr(
                analysis,
                "market_condition",
                "unknown",
            ),

            confirmations=confirmations,

            reasons=reasons + [
                "Risk reward requirement not satisfied"
            ],

            bullish_score=bullish_score,

            bearish_score=bearish_score,

            liquidity_score=liquidity_score,

            structure_score=structure_score,

            order_block_score=order_block_score,

            fvg_score=fvg_score,

            institutional_score=institutional_score,
        )

    # ==================================================
    # FINAL SIGNAL STRENGTH
    # ==================================================

    signal_strength = _determine_signal_strength(
        confidence=confidence,

        confirmations=confirmations,

        setup_available=True,
    )

    if signal_strength == "insufficient":

        final_signal = "no_trade"

        reasons.append(
            "Institutional setup strength is insufficient for execution"
        )

    else:

        final_signal = direction

    # ==================================================
    # FINAL RESPONSE
    # ==================================================

    return TradingSignal(
        symbol=normalized_symbol,

        timeframe=normalized_timeframe,

        current_price=current_price,

        signal=final_signal,

        confidence=confidence,

        signal_strength=signal_strength,

        entry_price=entry_price,

        entry_zone_low=zone_low,

        entry_zone_high=zone_high,

        stop_loss=stop_loss,

        take_profit_1=take_profit_1,

        take_profit_2=take_profit_2,

        risk_reward_1=risk_reward_1,

        risk_reward_2=risk_reward_2,

        invalidation_price=invalidation_price,

        market_condition=getattr(
            analysis,
            "market_condition",
            "unknown",
        ),

        confirmations=confirmations,

        reasons=reasons,

        bullish_score=bullish_score,

        bearish_score=bearish_score,

        liquidity_score=liquidity_score,

        structure_score=structure_score,

        order_block_score=order_block_score,

        fvg_score=fvg_score,

        institutional_score=institutional_score,
    )


# ======================================================
# SERIALIZE SIGNAL FOR API RESPONSE
# ======================================================

def serialize_trading_signal(
    signal: TradingSignal,
) -> dict:

    return {

        "symbol":
            signal.symbol,

        "timeframe":
            signal.timeframe,

        "current_price":
            str(
                signal.current_price
            ),

        "signal":
            signal.signal,

        "confidence":
            signal.confidence,

        "signal_strength":
            signal.signal_strength,

        "entry_price":
            (
                str(
                    signal.entry_price
                )
                if signal.entry_price is not None
                else None
            ),

        "entry_zone":
            (
                {
                    "low":
                        str(
                            signal.entry_zone_low
                        ),

                    "high":
                        str(
                            signal.entry_zone_high
                        ),
                }
                if (
                    signal.entry_zone_low
                    is not None
                    and
                    signal.entry_zone_high
                    is not None
                )
                else None
            ),

        "stop_loss":
            (
                str(
                    signal.stop_loss
                )
                if signal.stop_loss is not None
                else None
            ),

        "take_profit_1":
            (
                str(
                    signal.take_profit_1
                )
                if signal.take_profit_1 is not None
                else None
            ),

        "take_profit_2":
            (
                str(
                    signal.take_profit_2
                )
                if signal.take_profit_2 is not None
                else None
            ),

        "risk_reward_1":
            (
                str(
                    signal.risk_reward_1
                )
                if signal.risk_reward_1 is not None
                else None
            ),

        "risk_reward_2":
            (
                str(
                    signal.risk_reward_2
                )
                if signal.risk_reward_2 is not None
                else None
            ),

        "invalidation_price":
            (
                str(
                    signal.invalidation_price
                )
                if signal.invalidation_price is not None
                else None
            ),

        "market_condition":
            signal.market_condition,

        "confirmations":
            signal.confirmations,

        "reasons":
            signal.reasons,

        "bullish_score":
            signal.bullish_score,

        "bearish_score":
            signal.bearish_score,

        "institutional_score":
            signal.institutional_score,

        "institutional_metrics":
            {
                "liquidity_score":
                    signal.liquidity_score,

                "structure_score":
                    signal.structure_score,

                "order_block_score":
                    signal.order_block_score,

                "fvg_score":
                    signal.fvg_score,
            },
    }