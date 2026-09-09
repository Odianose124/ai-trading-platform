from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.services.mt5_trade_setup_service import (
    MT5TradeSetupError,
    mt5_trade_setup_service,
)
from app.services.risk_gate import risk_gate


@dataclass
class OpportunityScanResult:
    symbol: str
    timeframe: str
    mt5_symbol: str | None
    signal: str
    direction: str
    setup_quality: str
    confidence: float
    setup_status: str
    current_price: Decimal
    entry_price: Decimal
    stop_loss: Decimal
    take_profit_1: Decimal
    take_profit_2: Decimal
    risk_reward_1: Decimal
    risk_reward_2: Decimal
    overall_bias: str
    market_condition: str

    confirmations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    error: str | None = None

    # =====================================
    # RISK GATE DIAGNOSTICS
    # =====================================

    risk_gate_approved: bool = False
    risk_gate_status: str = "not_evaluated"
    risk_gate_reason: str | None = None
    risk_gate_broker_symbol: str | None = None
    risk_gate_risk_percent: Decimal = Decimal("0")
    risk_gate_spread_points: Decimal = Decimal("0")
    risk_gate_free_margin: Decimal = Decimal("0")
    risk_gate_risk_reward: Decimal = Decimal("0")

    risk_gate_reasons: list[str] = field(
        default_factory=list
    )

    risk_gate_warnings: list[str] = field(
        default_factory=list
    )

    risk_gate_errors: list[str] = field(
        default_factory=list
    )

    def serialize(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "mt5_symbol": self.mt5_symbol,
            "signal": self.signal,
            "direction": self.direction,
            "setup_quality": self.setup_quality,
            "confidence": self.confidence,
            "setup_status": self.setup_status,
            "current_price": str(self.current_price),
            "entry_price": str(self.entry_price),
            "stop_loss": str(self.stop_loss),
            "take_profit_1": str(self.take_profit_1),
            "take_profit_2": str(self.take_profit_2),
            "risk_reward_1": str(self.risk_reward_1),
            "risk_reward_2": str(self.risk_reward_2),
            "overall_bias": self.overall_bias,
            "market_condition": self.market_condition,
            "confirmations": self.confirmations,
            "warnings": self.warnings,
            "reasons": self.reasons,
            "error": self.error,
            "risk_gate_approved": self.risk_gate_approved,
            "risk_gate_status": self.risk_gate_status,
            "risk_gate_reason": self.risk_gate_reason,
            "risk_gate_broker_symbol": self.risk_gate_broker_symbol,
            "risk_gate_risk_percent": str(
                self.risk_gate_risk_percent
            ),
            "risk_gate_spread_points": str(
                self.risk_gate_spread_points
            ),
            "risk_gate_free_margin": str(
                self.risk_gate_free_margin
            ),
            "risk_gate_risk_reward": str(
                self.risk_gate_risk_reward
            ),
            "risk_gate_reasons": self.risk_gate_reasons,
            "risk_gate_warnings": self.risk_gate_warnings,
            "risk_gate_errors": self.risk_gate_errors,
        }


class OpportunityScannerError(Exception):
    pass


class OpportunityScannerService:
    """
    Scans multiple MT5 instruments using the existing
    MT5 trade setup engine.

    This service does not manufacture signals.

    This service does not execute trades.

    Pipeline:

        MT5 market data
            |
        MT5 trade setup
            |
        Opportunity result
            |
        Risk Gate
            |
        Executable opportunity

    Risk Gate also does not execute trades.
    """

    DEFAULT_TIMEFRAME = "15m"

    DEFAULT_SYMBOLS = (
        "XAUUSD",
        "EURUSD",
        "GBPUSD",
        "BTCUSD",
    )

    DEFAULT_RISK_PERCENT = Decimal("1.00")

    MIN_SETUP_RISK_REWARD_1 = Decimal("1.50")
    MIN_SETUP_RISK_REWARD_2 = Decimal("2.50")

    # =====================================
    # DECIMAL HELPER
    # =====================================

    @staticmethod
    def _decimal(
        value: Any,
        default: Decimal = Decimal("0"),
    ) -> Decimal:
        if value is None:
            return default

        if isinstance(value, Decimal):
            return value

        try:
            return Decimal(str(value))
        except Exception:
            return default

    # =====================================
    # SAFE LIST HELPER
    # =====================================

    @staticmethod
    def _string_list(
        value: Any,
    ) -> list[str]:
        if value is None:
            return []

        if isinstance(value, (list, tuple, set)):
            return [
                str(item)
                for item in value
                if item is not None
            ]

        return [str(value)]

    # =====================================
    # SETUP -> SCAN RESULT
    # =====================================

    def _result_from_setup(
        self,
        setup: Any,
    ) -> OpportunityScanResult:
        confidence = self._decimal(
            getattr(setup, "confidence", 0)
        )

        return OpportunityScanResult(
            symbol=str(setup.symbol),
            timeframe=str(setup.timeframe),
            mt5_symbol=getattr(
                setup,
                "mt5_symbol",
                None,
            ),
            signal=str(setup.signal),
            direction=str(setup.direction),
            setup_quality=str(
                setup.setup_quality
            ),
            confidence=float(confidence),
            setup_status=str(
                setup.setup_status
            ),
            current_price=self._decimal(
                setup.current_price
            ),
            entry_price=self._decimal(
                setup.entry_price
            ),
            stop_loss=self._decimal(
                setup.stop_loss
            ),
            take_profit_1=self._decimal(
                setup.take_profit_1
            ),
            take_profit_2=self._decimal(
                setup.take_profit_2
            ),
            risk_reward_1=self._decimal(
                setup.risk_reward_1
            ),
            risk_reward_2=self._decimal(
                setup.risk_reward_2
            ),
            overall_bias=str(
                setup.overall_bias
            ),
            market_condition=str(
                setup.market_condition
            ),
            confirmations=self._string_list(
                setup.confirmations
            ),
            warnings=self._string_list(
                setup.warnings
            ),
            reasons=self._string_list(
                setup.reasons
            ),
        )

    # =====================================
    # ERROR RESULT
    # =====================================

    def _error_result(
        self,
        symbol: str,
        timeframe: str,
        error: str,
    ) -> OpportunityScanResult:
        return OpportunityScanResult(
            symbol=symbol,
            timeframe=timeframe,
            mt5_symbol=None,
            signal="no_trade",
            direction="neutral",
            setup_quality="poor",
            confidence=0.0,
            setup_status="analysis_error",
            current_price=Decimal("0"),
            entry_price=Decimal("0"),
            stop_loss=Decimal("0"),
            take_profit_1=Decimal("0"),
            take_profit_2=Decimal("0"),
            risk_reward_1=Decimal("0"),
            risk_reward_2=Decimal("0"),
            overall_bias="unknown",
            market_condition="unknown",
            warnings=[
                "Opportunity scan could not complete for this symbol"
            ],
            reasons=[
                "MT5 trade setup analysis failed"
            ],
            error=error,
            risk_gate_approved=False,
            risk_gate_status="not_evaluated",
            risk_gate_reason=(
                "Risk Gate was not evaluated because "
                "trade setup analysis failed"
            ),
        )

    # =====================================
    # SINGLE SYMBOL SCAN
    # =====================================

    def scan_symbol(
        self,
        *,
        symbol: str,
        timeframe: str = DEFAULT_TIMEFRAME,
        limit: int = 500,
        strength: int = 2,
        lookback: int = 20,
        minimum_touches: int = 2,
    ) -> OpportunityScanResult:

        normalized_symbol = symbol.strip().upper()
        normalized_timeframe = timeframe.strip().lower()

        if not normalized_symbol:
            raise OpportunityScannerError(
                "Symbol is required"
            )

        if not normalized_timeframe:
            raise OpportunityScannerError(
                "Timeframe is required"
            )

        try:
            setup = mt5_trade_setup_service.analyze(
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
                limit=limit,
                strength=strength,
                lookback=lookback,
                minimum_touches=minimum_touches,
            )

            return self._result_from_setup(
                setup
            )

        except MT5TradeSetupError as exc:
            return self._error_result(
                normalized_symbol,
                normalized_timeframe,
                str(exc),
            )

        except Exception as exc:
            return self._error_result(
                normalized_symbol,
                normalized_timeframe,
                str(exc),
            )

    # =====================================
    # MULTI-SYMBOL SCAN
    # =====================================

    def scan(
        self,
        *,
        symbols: list[str] | tuple[str, ...] | None = None,
        timeframe: str = DEFAULT_TIMEFRAME,
        limit: int = 500,
        strength: int = 2,
        lookback: int = 20,
        minimum_touches: int = 2,
    ) -> list[OpportunityScanResult]:

        requested_symbols = (
            list(symbols)
            if symbols is not None
            else list(self.DEFAULT_SYMBOLS)
        )

        normalized_symbols: list[str] = []

        for symbol in requested_symbols:
            normalized = symbol.strip().upper()

            if (
                normalized
                and normalized not in normalized_symbols
            ):
                normalized_symbols.append(
                    normalized
                )

        if not normalized_symbols:
            raise OpportunityScannerError(
                "At least one symbol is required"
            )

        results: list[OpportunityScanResult] = []

        for symbol in normalized_symbols:
            result = self.scan_symbol(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                strength=strength,
                lookback=lookback,
                minimum_touches=minimum_touches,
            )

            results.append(result)

        return results

    # =====================================
    # RISK GATE EVALUATION
    # =====================================

    def _evaluate_risk_gate(
        self,
        result: OpportunityScanResult,
    ) -> dict[str, Any]:
        """
        Run the fully formed opportunity through
        the MT5 Risk Gate.

        This method does not execute anything.
        """

        return risk_gate.evaluate(
            {
                "symbol": result.symbol,
                "direction": result.direction,
                "confidence": result.confidence,
                "setup_quality": result.setup_quality,
                "risk_percent": float(
                    self.DEFAULT_RISK_PERCENT
                ),
                "entry_price": result.entry_price,
                "stop_loss": result.stop_loss,
                "take_profit_1": result.take_profit_1,
                "take_profit_2": result.take_profit_2,
            }
        )

    # =====================================
    # ATTACH RISK GATE RESULT
    # =====================================

    def _attach_risk_gate_result(
        self,
        result: OpportunityScanResult,
        risk_result: dict[str, Any],
    ) -> None:
        """
        Attach Risk Gate diagnostics to the scan result.

        A rejected opportunity remains visible in the
        scan results, while executable_opportunities()
        filters it out.
        """

        result.risk_gate_approved = bool(
            risk_result.get(
                "approved",
                False,
            )
        )

        result.risk_gate_status = str(
            risk_result.get(
                "status",
                "unknown",
            )
        )

        reason = risk_result.get("reason")

        if reason is not None:
            result.risk_gate_reason = str(
                reason
            )

        broker_symbol = risk_result.get(
            "broker_symbol"
        )

        if broker_symbol is not None:
            result.risk_gate_broker_symbol = str(
                broker_symbol
            )

        result.risk_gate_risk_percent = (
            self._decimal(
                risk_result.get(
                    "risk_percent"
                )
            )
        )

        result.risk_gate_spread_points = (
            self._decimal(
                risk_result.get(
                    "spread_points"
                )
            )
        )

        result.risk_gate_free_margin = (
            self._decimal(
                risk_result.get(
                    "free_margin"
                )
            )
        )

        result.risk_gate_risk_reward = (
            self._decimal(
                risk_result.get(
                    "risk_reward"
                )
            )
        )

        result.risk_gate_reasons = (
            self._string_list(
                risk_result.get(
                    "reasons"
                )
            )
        )

        result.risk_gate_warnings = (
            self._string_list(
                risk_result.get(
                    "warnings"
                )
            )
        )

        result.risk_gate_errors = (
            self._string_list(
                risk_result.get(
                    "errors"
                )
            )
        )

        if result.risk_gate_approved:
            approval_reason = (
                "Opportunity passed the MT5 Risk Gate"
            )

            if approval_reason not in result.reasons:
                result.reasons.append(
                    approval_reason
                )

        else:
            rejection_reason = (
                result.risk_gate_reason
                or "Opportunity rejected by the MT5 Risk Gate"
            )

            if rejection_reason not in result.warnings:
                result.warnings.append(
                    rejection_reason
                )

    # =====================================
    # SETUP ELIGIBILITY
    # =====================================

    def _is_risk_gate_eligible(
        self,
        result: OpportunityScanResult,
    ) -> tuple[bool, str | None]:

        if result.setup_status != "ready":
            return (
                False,
                "Trade setup is not ready",
            )

        if result.signal not in {
            "long",
            "short",
        }:
            return (
                False,
                "No executable trade signal",
            )

        if result.direction not in {
            "long",
            "short",
        }:
            return (
                False,
                "No executable trade direction",
            )

        if result.setup_quality == "poor":
            return (
                False,
                "Trade setup quality is poor",
            )

        if result.entry_price <= 0:
            return (
                False,
                "Entry price is invalid",
            )

        if result.stop_loss <= 0:
            return (
                False,
                "Stop-loss is invalid",
            )

        if result.take_profit_1 <= 0:
            return (
                False,
                "Take-profit 1 is invalid",
            )

        if result.take_profit_2 <= 0:
            return (
                False,
                "Take-profit 2 is invalid",
            )

        if (
            result.risk_reward_1
            < self.MIN_SETUP_RISK_REWARD_1
        ):
            return (
                False,
                "Setup risk/reward 1 is below "
                "the minimum requirement",
            )

        if (
            result.risk_reward_2
            < self.MIN_SETUP_RISK_REWARD_2
        ):
            return (
                False,
                "Setup risk/reward 2 is below "
                "the minimum requirement",
            )

        return True, None

    # =====================================
    # EVALUATE ALL READY OPPORTUNITIES
    # =====================================

    def evaluate_risk_gates(
        self,
        results: list[OpportunityScanResult],
    ) -> list[OpportunityScanResult]:
        """
        Evaluate Risk Gate for every structurally
        eligible setup.

        Results that are not ready are not sent through
        the Risk Gate because there is no executable
        trade geometry to validate.
        """

        for result in results:

            eligible, reason = (
                self._is_risk_gate_eligible(
                    result
                )
            )

            if not eligible:
                result.risk_gate_approved = False
                result.risk_gate_status = (
                    "not_evaluated"
                )
                result.risk_gate_reason = reason
                continue

            if (
                result.risk_gate_status
                not in {
                    "not_evaluated",
                    "",
                    "unknown",
                }
            ):
                continue

            try:
                risk_result = (
                    self._evaluate_risk_gate(
                        result
                    )
                )

                self._attach_risk_gate_result(
                    result,
                    risk_result,
                )

            except Exception as exc:

                result.risk_gate_approved = False

                result.risk_gate_status = (
                    "error"
                )

                result.risk_gate_reason = (
                    "Risk Gate evaluation failed"
                )

                result.risk_gate_errors = [
                    str(exc)
                ]

                if (
                    result.risk_gate_reason
                    not in result.warnings
                ):
                    result.warnings.append(
                        result.risk_gate_reason
                    )

        return results

    # =====================================
    # EXECUTABLE OPPORTUNITIES
    # =====================================

    def executable_opportunities(
        self,
        results: list[OpportunityScanResult],
    ) -> list[OpportunityScanResult]:
        """
        Return only opportunities that pass:

        1. MT5TradeSetupService
        2. Setup validation
        3. MT5 Risk Gate

        This method never executes an order.
        """

        self.evaluate_risk_gates(
            results
        )

        executable: list[
            OpportunityScanResult
        ] = []

        for result in results:

            eligible, _ = (
                self._is_risk_gate_eligible(
                    result
                )
            )

            if not eligible:
                continue

            if not result.risk_gate_approved:
                continue

            executable.append(
                result
            )

        return sorted(
            executable,
            key=lambda item: (
                item.confidence,
                float(item.risk_reward_2),
                float(item.risk_reward_1),
            ),
            reverse=True,
        )


opportunity_scanner_service = (
    OpportunityScannerService()
)