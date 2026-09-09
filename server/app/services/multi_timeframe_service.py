from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.ai_market_analysis_service import analyze_market
from app.services.candle_service import get_recent_candles
from app.services.timeframe_service import (
    TIMEFRAME_MINUTES,
    aggregate_candles,
)


@dataclass
class TimeframeAnalysis:
    timeframe: str
    bias: str
    confidence: int
    market_condition: str
    bullish_score: int
    bearish_score: int


@dataclass
class MultiTimeframeAnalysis:
    symbol: str
    primary_timeframe: str
    current_price: Decimal

    overall_bias: str
    confidence: int
    alignment: str

    higher_timeframe_bias: str
    execution_timeframe_bias: str

    analyses: list[TimeframeAnalysis]
    confirmations: list[str]
    conflicts: list[str]


TIMEFRAME_SEQUENCE = [
    "1m",
    "5m",
    "15m",
    "1h",
    "4h",
]


TIMEFRAME_WEIGHTS = {
    "1m": 1,
    "5m": 1,
    "15m": 2,
    "1h": 3,
    "4h": 4,
}


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


def _normalize_bias(bias: str) -> str:
    value = str(bias).strip().lower()

    if value == "long":
        return "bullish"

    if value == "short":
        return "bearish"

    if value == "bullish":
        return "bullish"

    if value == "bearish":
        return "bearish"

    return "neutral"


def _calculate_alignment(
    analyses: list[TimeframeAnalysis],
) -> tuple[str, int]:
    """
    Calculate directional alignment using only timeframes
    that have sufficient data and a directional bias.

    Confidence is included so a highly confident timeframe
    contributes more than a weak directional timeframe.
    """

    directional = [
        analysis
        for analysis in analyses
        if (
            analysis.bias in {"bullish", "bearish"}
            and analysis.confidence > 0
            and analysis.market_condition != "insufficient_data"
        )
    ]

    if not directional:
        return "no_direction", 0

    bullish_strength = sum(
        analysis.confidence
        for analysis in directional
        if analysis.bias == "bullish"
    )

    bearish_strength = sum(
        analysis.confidence
        for analysis in directional
        if analysis.bias == "bearish"
    )

    total_strength = (
        bullish_strength
        + bearish_strength
    )

    if total_strength <= 0:
        return "no_direction", 0

    if bullish_strength > bearish_strength:
        dominant_strength = bullish_strength
        alignment = "bullish_aligned"

    elif bearish_strength > bullish_strength:
        dominant_strength = bearish_strength
        alignment = "bearish_aligned"

    else:
        return "conflicted", 0

    alignment_score = round(
        (
            dominant_strength
            / total_strength
        )
        * 100
    )

    return (
        alignment,
        min(100, alignment_score),
    )


def _calculate_weighted_bias(
    analyses: list[TimeframeAnalysis],
) -> tuple[str, int]:
    """
    Calculate the weighted multi-timeframe directional bias.

    Timeframe weights:

        1m  = 1
        5m  = 1
        15m = 2
        1h  = 3
        4h  = 4

    The timeframe weight determines importance while the
    individual analysis confidence determines signal strength.
    """

    bullish_weight = 0.0
    bearish_weight = 0.0

    valid_analyses = [
        analysis
        for analysis in analyses
        if (
            analysis.bias in {"bullish", "bearish"}
            and analysis.confidence > 0
            and analysis.market_condition != "insufficient_data"
        )
    ]

    if not valid_analyses:
        return "neutral", 0

    for analysis in valid_analyses:
        timeframe_weight = TIMEFRAME_WEIGHTS.get(
            analysis.timeframe,
            1,
        )

        confidence = max(
            0,
            min(
                analysis.confidence,
                100,
            ),
        )

        weighted_value = (
            timeframe_weight
            * (confidence / 100)
        )

        if analysis.bias == "bullish":
            bullish_weight += weighted_value

        elif analysis.bias == "bearish":
            bearish_weight += weighted_value

    directional_total = (
        bullish_weight
        + bearish_weight
    )

    if directional_total <= 0:
        return "neutral", 0

    difference = abs(
        bullish_weight
        - bearish_weight
    )

    confidence = round(
        (
            difference
            / directional_total
        )
        * 100
    )

    if bullish_weight > bearish_weight:
        return (
            "bullish",
            min(100, confidence),
        )

    if bearish_weight > bullish_weight:
        return (
            "bearish",
            min(100, confidence),
        )

    return "neutral", 0


def _calculate_higher_timeframe_bias(
    analyses: list[TimeframeAnalysis],
) -> str:
    """
    Determine the higher-timeframe bias from 1h and 4h.

    4h receives more influence than 1h.

    Only timeframes with sufficient data and a directional
    bias are considered.
    """

    higher_timeframes = [
        analysis
        for analysis in analyses
        if (
            analysis.timeframe in {"1h", "4h"}
            and analysis.bias in {"bullish", "bearish"}
            and analysis.confidence > 0
            and analysis.market_condition != "insufficient_data"
        )
    ]

    if not higher_timeframes:
        return "neutral"

    bullish_weight = 0.0
    bearish_weight = 0.0

    for analysis in higher_timeframes:
        weight = TIMEFRAME_WEIGHTS.get(
            analysis.timeframe,
            1,
        )

        strength = (
            analysis.confidence
            / 100
        )

        weighted_value = (
            weight
            * strength
        )

        if analysis.bias == "bullish":
            bullish_weight += weighted_value

        elif analysis.bias == "bearish":
            bearish_weight += weighted_value

    if bullish_weight > bearish_weight:
        return "bullish"

    if bearish_weight > bullish_weight:
        return "bearish"

    return "neutral"


def _calculate_final_confidence(
    analyses: list[TimeframeAnalysis],
    alignment_score: int,
    weighted_confidence: int,
    primary_timeframe: str,
    higher_timeframe_bias: str,
    weighted_bias: str,
    conflicts: list[str],
) -> int:
    """
    Produce the final MTF confidence.

    Components:

        50% weighted timeframe confidence
        25% directional alignment
        15% execution timeframe confidence
        10% higher-timeframe confirmation

    Missing timeframes are excluded from the mathematical
    confidence calculation rather than treated as bullish
    or bearish.

    Conflicts reduce the final confidence.
    """

    valid_analyses = [
        analysis
        for analysis in analyses
        if (
            analysis.market_condition != "insufficient_data"
            and analysis.confidence > 0
            and analysis.bias in {"bullish", "bearish"}
        )
    ]

    if not valid_analyses:
        return 0

    primary_analysis = next(
        (
            analysis
            for analysis in analyses
            if analysis.timeframe
            == primary_timeframe
        ),
        None,
    )

    execution_confidence = (
        primary_analysis.confidence
        if primary_analysis is not None
        and primary_analysis.bias
        in {"bullish", "bearish"}
        else 0
    )

    higher_confirmation_score = 0

    if (
        weighted_bias in {"bullish", "bearish"}
        and higher_timeframe_bias
        == weighted_bias
    ):
        higher_confirmation_score = 100

    elif higher_timeframe_bias == "neutral":
        higher_confirmation_score = 50

    else:
        higher_confirmation_score = 0

    confidence = round(
        (
            weighted_confidence * 0.50
            + alignment_score * 0.25
            + execution_confidence * 0.15
            + higher_confirmation_score * 0.10
        )
    )

    # ---------------------------------------------------------
    # DATA-COMPLETENESS PENALTY
    # ---------------------------------------------------------

    expected_timeframes = len(
        TIMEFRAME_SEQUENCE
    )

    available_timeframes = len(
        [
            analysis
            for analysis in analyses
            if analysis.market_condition
            != "insufficient_data"
        ]
    )

    data_completeness = (
        available_timeframes
        / expected_timeframes
    )

    confidence = round(
        confidence
        * (
            0.75
            + (
                0.25
                * data_completeness
            )
        )
    )

    # ---------------------------------------------------------
    # CONFLICT PENALTY
    # ---------------------------------------------------------

    if conflicts:
        confidence = round(
            confidence * 0.60
        )

    # ---------------------------------------------------------
    # PREVENT ARTIFICIAL 100%
    # ---------------------------------------------------------

    # 100% confidence is reserved for a separate future
    # institutional-grade probability model. The current
    # deterministic confluence engine should not report 100%
    # simply because the available timeframes agree.
    confidence = min(
        confidence,
        95,
    )

    return max(
        0,
        min(
            confidence,
            100,
        ),
    )


def analyze_multi_timeframe(
    db,
    symbol: str,
    primary_timeframe: str,
    current_price: Decimal,
    limit: int = 200,
) -> MultiTimeframeAnalysis:
    normalized_symbol = symbol.strip().upper()

    normalized_primary = (
        primary_timeframe
        .strip()
        .lower()
    )

    if normalized_primary not in TIMEFRAME_MINUTES:
        raise ValueError(
            f"Unsupported timeframe: {normalized_primary}"
        )

    analyses: list[TimeframeAnalysis] = []

    # ---------------------------------------------------------
    # ANALYZE EACH TIMEFRAME
    # ---------------------------------------------------------

    for timeframe in TIMEFRAME_SEQUENCE:
        candles = _load_candles(
            db=db,
            symbol=normalized_symbol,
            timeframe=timeframe,
            limit=limit,
        )

        if len(candles) < 20:
            analyses.append(
                TimeframeAnalysis(
                    timeframe=timeframe,
                    bias="neutral",
                    confidence=0,
                    market_condition="insufficient_data",
                    bullish_score=0,
                    bearish_score=0,
                )
            )
            continue

        analysis = analyze_market(
            db=db,
            symbol=normalized_symbol,
            timeframe=timeframe,
            current_price=current_price,
            limit=limit,
        )

        analyses.append(
            TimeframeAnalysis(
                timeframe=timeframe,
                bias=_normalize_bias(
                    analysis.bias
                ),
                confidence=max(
                    0,
                    min(
                        analysis.confidence,
                        100,
                    ),
                ),
                market_condition=(
                    analysis.market_condition
                ),
                bullish_score=(
                    analysis.bullish_score
                ),
                bearish_score=(
                    analysis.bearish_score
                ),
            )
        )

    # ---------------------------------------------------------
    # DIRECTIONAL ALIGNMENT
    # ---------------------------------------------------------

    alignment, alignment_score = (
        _calculate_alignment(
            analyses
        )
    )

    # ---------------------------------------------------------
    # WEIGHTED BIAS
    # ---------------------------------------------------------

    weighted_bias, weighted_confidence = (
        _calculate_weighted_bias(
            analyses
        )
    )

    # ---------------------------------------------------------
    # PRIMARY / EXECUTION TIMEFRAME
    # ---------------------------------------------------------

    primary_analysis = next(
        (
            analysis
            for analysis in analyses
            if analysis.timeframe
            == normalized_primary
        ),
        None,
    )

    execution_timeframe_bias = (
        primary_analysis.bias
        if primary_analysis is not None
        else "neutral"
    )

    # ---------------------------------------------------------
    # HIGHER-TIMEFRAME BIAS
    # ---------------------------------------------------------

    higher_timeframe_bias = (
        _calculate_higher_timeframe_bias(
            analyses
        )
    )

    # ---------------------------------------------------------
    # CONFIRMATIONS
    # ---------------------------------------------------------

    confirmations: list[str] = []

    conflicts: list[str] = []

    bullish_timeframes = [
        analysis.timeframe
        for analysis in analyses
        if (
            analysis.bias == "bullish"
            and analysis.market_condition
            != "insufficient_data"
        )
    ]

    bearish_timeframes = [
        analysis.timeframe
        for analysis in analyses
        if (
            analysis.bias == "bearish"
            and analysis.market_condition
            != "insufficient_data"
        )
    ]

    insufficient_timeframes = [
        analysis.timeframe
        for analysis in analyses
        if analysis.market_condition
        == "insufficient_data"
    ]

    if bullish_timeframes:
        confirmations.append(
            "bullish_timeframes:"
            + ",".join(
                bullish_timeframes
            )
        )

    if bearish_timeframes:
        confirmations.append(
            "bearish_timeframes:"
            + ",".join(
                bearish_timeframes
            )
        )

    if (
        weighted_bias == "bullish"
        and higher_timeframe_bias == "bullish"
    ):
        confirmations.append(
            "higher_timeframe_bullish_confirmation"
        )

    elif (
        weighted_bias == "bearish"
        and higher_timeframe_bias == "bearish"
    ):
        confirmations.append(
            "higher_timeframe_bearish_confirmation"
        )

    if insufficient_timeframes:
        confirmations.append(
            "insufficient_data:"
            + ",".join(
                insufficient_timeframes
            )
        )

    # ---------------------------------------------------------
    # CONFLICT DETECTION
    # ---------------------------------------------------------

    if (
        primary_analysis is not None
        and primary_analysis.bias
        in {"bullish", "bearish"}
        and higher_timeframe_bias
        in {"bullish", "bearish"}
        and primary_analysis.bias
        != higher_timeframe_bias
    ):
        conflicts.append(
            "primary_timeframe_conflicts_with_higher_timeframes"
        )

    if alignment == "conflicted":
        conflicts.append(
            "timeframes_are_directionally_conflicted"
        )

    if (
        weighted_bias in {"bullish", "bearish"}
        and primary_analysis is not None
        and primary_analysis.bias
        in {"bullish", "bearish"}
        and primary_analysis.bias
        != weighted_bias
    ):
        conflicts.append(
            "primary_timeframe_conflicts_with_weighted_bias"
        )

    # ---------------------------------------------------------
    # OVERALL BIAS
    # ---------------------------------------------------------

    if conflicts:
        overall_bias = "neutral"

    elif weighted_bias == "bullish":
        overall_bias = "bullish"

    elif weighted_bias == "bearish":
        overall_bias = "bearish"

    else:
        overall_bias = "neutral"

    # ---------------------------------------------------------
    # FINAL CONFIDENCE
    # ---------------------------------------------------------

    confidence = _calculate_final_confidence(
        analyses=analyses,
        alignment_score=alignment_score,
        weighted_confidence=weighted_confidence,
        primary_timeframe=normalized_primary,
        higher_timeframe_bias=higher_timeframe_bias,
        weighted_bias=weighted_bias,
        conflicts=conflicts,
    )

    # A neutral overall bias should never carry a strong
    # directional confidence score.
    if overall_bias == "neutral":
        confidence = min(
            confidence,
            49,
        )

    # ---------------------------------------------------------
    # FINAL RESULT
    # ---------------------------------------------------------

    return MultiTimeframeAnalysis(
        symbol=normalized_symbol,
        primary_timeframe=normalized_primary,
        current_price=current_price,
        overall_bias=overall_bias,
        confidence=confidence,
        alignment=alignment,
        higher_timeframe_bias=higher_timeframe_bias,
        execution_timeframe_bias=execution_timeframe_bias,
        analyses=analyses,
        confirmations=confirmations,
        conflicts=conflicts,
    )


def serialize_multi_timeframe_analysis(
    analysis: MultiTimeframeAnalysis,
) -> dict:
    return {
        "symbol": analysis.symbol,
        "primary_timeframe": (
            analysis.primary_timeframe
        ),
        "current_price": analysis.current_price,
        "overall_bias": analysis.overall_bias,
        "confidence": analysis.confidence,
        "alignment": analysis.alignment,
        "higher_timeframe_bias": (
            analysis.higher_timeframe_bias
        ),
        "execution_timeframe_bias": (
            analysis.execution_timeframe_bias
        ),
        "analyses": [
            {
                "timeframe": item.timeframe,
                "bias": item.bias,
                "confidence": item.confidence,
                "market_condition": (
                    item.market_condition
                ),
                "bullish_score": (
                    item.bullish_score
                ),
                "bearish_score": (
                    item.bearish_score
                ),
            }
            for item in analysis.analyses
        ],
        "confirmations": analysis.confirmations,
        "conflicts": analysis.conflicts,
    }