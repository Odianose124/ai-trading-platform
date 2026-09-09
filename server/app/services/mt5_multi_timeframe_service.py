from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.services.mt5_ai_market_analysis_service import (
    MT5AIMarketAnalysisError,
    mt5_ai_market_analysis_service,
)


TIMEFRAME_SEQUENCE = ["1m", "5m", "15m", "1h", "4h"]

TIMEFRAME_WEIGHTS = {
    "1m": 1,
    "5m": 2,
    "15m": 4,
    "1h": 6,
    "4h": 8,
}

EXECUTION_TIMEFRAME = "15m"

HIGHER_TIMEFRAMES = {"1h", "4h"}

LOWER_TIMEFRAMES = {"1m", "5m"}


@dataclass
class MT5TimeframeAnalysis:
    timeframe: str
    bias: str
    confidence: float
    market_condition: str
    bullish_score: float
    bearish_score: float
    signal_strength: float
    status: str
    error: str | None = None


@dataclass
class MT5MultiTimeframeAnalysis:
    symbol: str
    primary_timeframe: str
    current_price: float
    overall_bias: str
    confidence: float
    alignment: str
    higher_timeframe_bias: str
    execution_timeframe_bias: str
    analyses: list[MT5TimeframeAnalysis]
    confirmations: list[str]
    conflicts: list[str]
    warnings: list[str]


class MT5MultiTimeframeAnalysisError(RuntimeError):
    pass


class MT5MultiTimeframeService:

    def _normalize_timeframe(self, timeframe: str) -> str:
        normalized = timeframe.strip().lower()

        if normalized not in TIMEFRAME_SEQUENCE:
            raise MT5MultiTimeframeAnalysisError(
                f"Unsupported primary timeframe: {timeframe}. "
                f"Supported timeframes: {', '.join(TIMEFRAME_SEQUENCE)}"
            )

        return normalized

    def _build_timeframe_analysis(
        self,
        timeframe: str,
        serialized_analysis: dict[str, Any],
    ) -> MT5TimeframeAnalysis:

        bias = str(
            serialized_analysis.get("overall_bias", "neutral")
        ).strip().lower()

        confidence = float(
            serialized_analysis.get("confidence", 0)
        )

        market_condition = str(
            serialized_analysis.get(
                "market_condition",
                "range_or_uncertain",
            )
        ).strip().lower()

        scores = serialized_analysis.get("scores", {})

        bullish_score = float(
            scores.get("bullish", 0)
        )

        bearish_score = float(
            scores.get("bearish", 0)
        )

        score_difference = abs(
            bullish_score - bearish_score
        )

        total_score = bullish_score + bearish_score

        if total_score > 0:
            signal_strength = min(
                100.0,
                (score_difference / total_score) * 100.0,
            )
        else:
            signal_strength = 0.0

        if bias in {"bullish", "bearish"} and confidence >= 50:
            status = "confirmed"

        elif bias in {"bullish", "bearish"}:
            status = "uncertain"

        else:
            status = "neutral"

        return MT5TimeframeAnalysis(
            timeframe=timeframe,
            bias=bias,
            confidence=round(confidence, 4),
            market_condition=market_condition,
            bullish_score=round(bullish_score, 4),
            bearish_score=round(bearish_score, 4),
            signal_strength=round(signal_strength, 4),
            status=status,
            error=None,
        )

    def _get_confirmed_analyses(
        self,
        analyses: list[MT5TimeframeAnalysis],
    ) -> list[MT5TimeframeAnalysis]:

        return [
            analysis
            for analysis in analyses
            if analysis.status == "confirmed"
            and analysis.bias in {"bullish", "bearish"}
        ]

    def _weighted_bias(
        self,
        analyses: list[MT5TimeframeAnalysis],
    ) -> tuple[str, float, float]:

        confirmed = self._get_confirmed_analyses(analyses)

        if not confirmed:
            return "neutral", 0.0, 0.0

        bullish_weight = 0.0
        bearish_weight = 0.0

        weighted_confidence = 0.0
        total_weight = 0.0

        for analysis in confirmed:
            weight = TIMEFRAME_WEIGHTS.get(
                analysis.timeframe,
                1,
            )

            total_weight += weight
            weighted_confidence += (
                analysis.confidence * weight
            )

            if analysis.bias == "bullish":
                bullish_weight += weight

            elif analysis.bias == "bearish":
                bearish_weight += weight

        if bullish_weight > bearish_weight:
            bias = "bullish"
        elif bearish_weight > bullish_weight:
            bias = "bearish"
        else:
            bias = "neutral"

        if total_weight > 0:
            confidence = weighted_confidence / total_weight
        else:
            confidence = 0.0

        return (
            bias,
            confidence,
            total_weight,
        )

    def _calculate_alignment(
        self,
        analyses: list[MT5TimeframeAnalysis],
        overall_bias: str,
        higher_timeframe_bias: str,
        execution_timeframe_bias: str,
    ) -> tuple[str, float]:

        confirmed = self._get_confirmed_analyses(
            analyses
        )

        if not confirmed or overall_bias == "neutral":
            return "mixed", 0.0

        total_weight = 0.0
        aligned_weight = 0.0

        opposing_timeframes: list[str] = []

        for analysis in confirmed:
            weight = TIMEFRAME_WEIGHTS.get(
                analysis.timeframe,
                1,
            )

            total_weight += weight

            if analysis.bias == overall_bias:
                aligned_weight += weight
            else:
                opposing_timeframes.append(
                    analysis.timeframe
                )

        if total_weight <= 0:
            return "mixed", 0.0

        alignment_score = (
            aligned_weight / total_weight
        ) * 100.0

        opposing_set = set(opposing_timeframes)

        higher_conflict = bool(
            opposing_set & HIGHER_TIMEFRAMES
        )

        execution_conflict = (
            EXECUTION_TIMEFRAME in opposing_set
        )

        lower_conflict = bool(
            opposing_set & LOWER_TIMEFRAMES
        )

        if higher_conflict:
            return (
                f"{overall_bias}_with_higher_timeframe_conflict",
                alignment_score,
            )

        if execution_conflict:
            return (
                f"{overall_bias}_with_execution_timeframe_conflict",
                alignment_score,
            )

        if lower_conflict:
            return (
                f"{overall_bias}_with_lower_timeframe_conflict",
                alignment_score,
            )

        if alignment_score >= 80:
            return (
                f"{overall_bias}_strongly_aligned",
                alignment_score,
            )

        if alignment_score >= 60:
            return (
                f"{overall_bias}_aligned",
                alignment_score,
            )

        if alignment_score >= 50:
            return (
                f"{overall_bias}_partially_aligned",
                alignment_score,
            )

        return (
            "mixed",
            alignment_score,
        )

    def _higher_timeframe_bias(
        self,
        analyses: list[MT5TimeframeAnalysis],
    ) -> str:

        higher = [
            analysis
            for analysis in analyses
            if analysis.timeframe in HIGHER_TIMEFRAMES
            and analysis.status == "confirmed"
            and analysis.bias in {"bullish", "bearish"}
        ]

        if not higher:
            return "neutral"

        bullish_weight = 0
        bearish_weight = 0

        for analysis in higher:
            weight = TIMEFRAME_WEIGHTS.get(
                analysis.timeframe,
                1,
            )

            if analysis.bias == "bullish":
                bullish_weight += weight

            elif analysis.bias == "bearish":
                bearish_weight += weight

        if bullish_weight > bearish_weight:
            return "bullish"

        if bearish_weight > bullish_weight:
            return "bearish"

        return "neutral"

    def _execution_timeframe_bias(
        self,
        analyses: list[MT5TimeframeAnalysis],
    ) -> str:

        execution = next(
            (
                analysis
                for analysis in analyses
                if analysis.timeframe
                == EXECUTION_TIMEFRAME
            ),
            None,
        )

        if execution is None:
            return "neutral"

        if execution.status != "confirmed":
            return "neutral"

        if execution.bias not in {"bullish", "bearish"}:
            return "neutral"

        return execution.bias

    def _calculate_confidence(
        self,
        analyses: list[MT5TimeframeAnalysis],
        overall_bias: str,
        higher_timeframe_bias: str,
        execution_timeframe_bias: str,
        alignment_score: float,
    ) -> float:

        if overall_bias == "neutral":
            return 0.0

        confirmed = self._get_confirmed_analyses(
            analyses
        )

        if not confirmed:
            return 0.0

        total_weight = 0.0
        weighted_confidence = 0.0

        directional_strength = 0.0

        for analysis in confirmed:

            weight = TIMEFRAME_WEIGHTS.get(
                analysis.timeframe,
                1,
            )

            total_weight += weight

            weighted_confidence += (
                analysis.confidence * weight
            )

            directional_strength += (
                analysis.signal_strength * weight
            )

        if total_weight <= 0:
            return 0.0

        weighted_confidence /= total_weight

        directional_strength /= total_weight

        confirmed_count = len(confirmed)

        if confirmed_count >= 4:
            evidence_cap = 90.0
        elif confirmed_count == 3:
            evidence_cap = 82.0
        elif confirmed_count == 2:
            evidence_cap = 70.0
        else:
            evidence_cap = 55.0

        confidence = (
            weighted_confidence * 0.45
            + directional_strength * 0.20
            + alignment_score * 0.20
        )

        if (
            higher_timeframe_bias == overall_bias
        ):
            confidence += 10.0

        if (
            execution_timeframe_bias == overall_bias
        ):
            confidence += 8.0

        elif (
            execution_timeframe_bias
            not in {"neutral", overall_bias}
        ):
            confidence *= 0.75

        if (
            higher_timeframe_bias
            not in {"neutral", overall_bias}
        ):
            confidence *= 0.70

        opposing = [
            analysis
            for analysis in confirmed
            if analysis.bias != overall_bias
        ]

        if opposing:

            for analysis in opposing:

                if analysis.timeframe in HIGHER_TIMEFRAMES:
                    confidence *= 0.70

                elif (
                    analysis.timeframe
                    == EXECUTION_TIMEFRAME
                ):
                    confidence *= 0.85

                else:
                    # Lower-timeframe countertrend pressure
                    # is treated as timing risk rather than
                    # a complete directional invalidation.
                    confidence *= 0.97

        confidence = min(
            confidence,
            evidence_cap,
            95.0,
        )

        return round(
            max(confidence, 0.0),
            4,
        )

    def _build_confirmations(
        self,
        analyses: list[MT5TimeframeAnalysis],
        overall_bias: str,
        higher_timeframe_bias: str,
        execution_timeframe_bias: str,
    ) -> list[str]:

        confirmations: list[str] = []

        confirmed = self._get_confirmed_analyses(
            analyses
        )

        aligned = [
            analysis.timeframe
            for analysis in confirmed
            if analysis.bias == overall_bias
        ]

        if aligned:
            confirmations.append(
                "aligned_timeframes:"
                + ",".join(aligned)
            )

        if (
            higher_timeframe_bias == overall_bias
        ):
            confirmations.append(
                "higher_timeframe_confirmation"
            )

        if (
            execution_timeframe_bias
            == overall_bias
        ):
            confirmations.append(
                "execution_timeframe_confirmation"
            )

        return confirmations

    def _build_conflicts(
        self,
        analyses: list[MT5TimeframeAnalysis],
        overall_bias: str,
    ) -> list[str]:

        conflicts: list[str] = []

        confirmed = self._get_confirmed_analyses(
            analyses
        )

        opposing = [
            analysis.timeframe
            for analysis in confirmed
            if analysis.bias != overall_bias
        ]

        if opposing:
            conflicts.append(
                "opposing_timeframes:"
                + ",".join(opposing)
            )

        return conflicts

    def _build_warnings(
        self,
        analyses: list[MT5TimeframeAnalysis],
        overall_bias: str,
        higher_timeframe_bias: str,
        execution_timeframe_bias: str,
    ) -> list[str]:

        warnings: list[str] = []

        confirmed = self._get_confirmed_analyses(
            analyses
        )

        opposing = [
            analysis
            for analysis in confirmed
            if analysis.bias != overall_bias
        ]

        higher_conflicts = [
            analysis.timeframe
            for analysis in opposing
            if analysis.timeframe
            in HIGHER_TIMEFRAMES
        ]

        execution_conflicts = [
            analysis.timeframe
            for analysis in opposing
            if analysis.timeframe
            == EXECUTION_TIMEFRAME
        ]

        lower_conflicts = [
            analysis.timeframe
            for analysis in opposing
            if analysis.timeframe
            in LOWER_TIMEFRAMES
        ]

        if higher_conflicts:
            warnings.append(
                "Higher-timeframe directional conflict exists on: "
                + ", ".join(higher_conflicts)
            )

        if execution_conflicts:
            warnings.append(
                "Execution-timeframe directional conflict exists on: "
                + ", ".join(execution_conflicts)
                + "; entry execution should be treated as high risk"
            )

        if lower_conflicts:
            warnings.append(
                "Lower-timeframe countertrend pressure exists on: "
                + ", ".join(lower_conflicts)
                + "; this may affect entry timing without invalidating the higher-timeframe bias"
            )

        uncertain = [
            analysis.timeframe
            for analysis in analyses
            if analysis.status == "uncertain"
        ]

        if uncertain:
            warnings.append(
                "Insufficient directional confirmation on: "
                + ", ".join(uncertain)
            )

        if (
            overall_bias != "neutral"
            and higher_timeframe_bias == "neutral"
        ):
            warnings.append(
                "Higher-timeframe direction is not sufficiently confirmed"
            )

        if (
            overall_bias != "neutral"
            and execution_timeframe_bias == "neutral"
        ):
            warnings.append(
                "Execution timeframe does not currently provide confirmed directional evidence"
            )

        return warnings

    def analyze(
        self,
        symbol: str,
        primary_timeframe: str = "15m",
        limit: int = 500,
        strength: int = 2,
        lookback: int = 20,
        minimum_touches: int = 2,
    ) -> MT5MultiTimeframeAnalysis:

        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise MT5MultiTimeframeAnalysisError(
                "Trading symbol cannot be empty"
            )

        if limit < 100:
            raise MT5MultiTimeframeAnalysisError(
                "Candle limit must be at least 100"
            )

        if strength < 1:
            raise MT5MultiTimeframeAnalysisError(
                "Strength must be at least 1"
            )

        if lookback < 1:
            raise MT5MultiTimeframeAnalysisError(
                "Lookback must be at least 1"
            )

        if minimum_touches < 1:
            raise MT5MultiTimeframeAnalysisError(
                "Minimum touches must be at least 1"
            )

        normalized_primary_timeframe = (
            self._normalize_timeframe(
                primary_timeframe
            )
        )

        analyses: list[
            MT5TimeframeAnalysis
        ] = []

        current_price: float | None = None

        for timeframe in TIMEFRAME_SEQUENCE:

            try:

                serialized = (
                    mt5_ai_market_analysis_service.analyze(
                        symbol=normalized_symbol,
                        timeframe=timeframe,
                        limit=limit,
                        strength=strength,
                        lookback=lookback,
                        minimum_touches=minimum_touches,
                    )
                )

                serialized_analysis = (
                    mt5_ai_market_analysis_service.serialize(
                        serialized
                    )
                )

                if current_price is None:

                    market_data = (
                        serialized_analysis.get(
                            "market",
                            {},
                        )
                    )

                    current_price_value = (
                        market_data.get(
                            "bid"
                        )
                        or market_data.get(
                            "ask"
                        )
                        or market_data.get(
                            "current_price"
                        )
                    )

                    if current_price_value is not None:
                        current_price = float(
                            current_price_value
                        )

                timeframe_analysis = (
                    self._build_timeframe_analysis(
                        timeframe=timeframe,
                        serialized_analysis=serialized_analysis,
                    )
                )

                analyses.append(
                    timeframe_analysis
                )

            except (
                MT5AIMarketAnalysisError,
                Exception,
            ) as exc:

                analyses.append(
                    MT5TimeframeAnalysis(
                        timeframe=timeframe,
                        bias="neutral",
                        confidence=0.0,
                        market_condition="unavailable",
                        bullish_score=0.0,
                        bearish_score=0.0,
                        signal_strength=0.0,
                        status="unavailable",
                        error=str(exc),
                    )
                )

        if current_price is None:
            raise MT5MultiTimeframeAnalysisError(
                f"Unable to determine current MT5 price for {normalized_symbol}"
            )

        (
            overall_bias,
            _,
            _,
        ) = self._weighted_bias(
            analyses
        )

        higher_timeframe_bias = (
            self._higher_timeframe_bias(
                analyses
            )
        )

        execution_timeframe_bias = (
            self._execution_timeframe_bias(
                analyses
            )
        )

        (
            alignment,
            alignment_score,
        ) = self._calculate_alignment(
            analyses=analyses,
            overall_bias=overall_bias,
            higher_timeframe_bias=higher_timeframe_bias,
            execution_timeframe_bias=execution_timeframe_bias,
        )

        confidence = self._calculate_confidence(
            analyses=analyses,
            overall_bias=overall_bias,
            higher_timeframe_bias=higher_timeframe_bias,
            execution_timeframe_bias=execution_timeframe_bias,
            alignment_score=alignment_score,
        )

        confirmations = self._build_confirmations(
            analyses=analyses,
            overall_bias=overall_bias,
            higher_timeframe_bias=higher_timeframe_bias,
            execution_timeframe_bias=execution_timeframe_bias,
        )

        conflicts = self._build_conflicts(
            analyses=analyses,
            overall_bias=overall_bias,
        )

        warnings = self._build_warnings(
            analyses=analyses,
            overall_bias=overall_bias,
            higher_timeframe_bias=higher_timeframe_bias,
            execution_timeframe_bias=execution_timeframe_bias,
        )

        return MT5MultiTimeframeAnalysis(
            symbol=normalized_symbol,
            primary_timeframe=normalized_primary_timeframe,
            current_price=current_price,
            overall_bias=overall_bias,
            confidence=confidence,
            alignment=alignment,
            higher_timeframe_bias=higher_timeframe_bias,
            execution_timeframe_bias=execution_timeframe_bias,
            analyses=analyses,
            confirmations=confirmations,
            conflicts=conflicts,
            warnings=warnings,
        )

    def serialize(
        self,
        analysis: MT5MultiTimeframeAnalysis,
    ) -> dict[str, Any]:

        return {
            "symbol": analysis.symbol,
            "primary_timeframe": analysis.primary_timeframe,
            "current_price": analysis.current_price,
            "overall_bias": analysis.overall_bias,
            "confidence": analysis.confidence,
            "alignment": analysis.alignment,
            "higher_timeframe_bias": analysis.higher_timeframe_bias,
            "execution_timeframe_bias": analysis.execution_timeframe_bias,
            "analyses": [
                {
                    "timeframe": item.timeframe,
                    "bias": item.bias,
                    "confidence": item.confidence,
                    "market_condition": item.market_condition,
                    "bullish_score": item.bullish_score,
                    "bearish_score": item.bearish_score,
                    "signal_strength": item.signal_strength,
                    "status": item.status,
                    "error": item.error,
                }
                for item in analysis.analyses
            ],
            "confirmations": analysis.confirmations,
            "conflicts": analysis.conflicts,
            "warnings": analysis.warnings,
        }


mt5_multi_timeframe_service = (
    MT5MultiTimeframeService()
)