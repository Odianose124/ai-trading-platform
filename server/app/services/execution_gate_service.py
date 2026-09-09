from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.services.risk_management_service import assess_risk
from app.services.trade_setup_service import TradeSetup


MIN_EXECUTION_CONFIDENCE = 65
APPROVED_SETUP_QUALITIES = {"good", "high"}

DEFAULT_EXECUTION_RISK_PERCENT = Decimal("1.00")
DEFAULT_EXECUTION_LEVERAGE = Decimal("1.00")


@dataclass
class ExecutionDecision:
    execution_allowed: bool

    symbol: str
    timeframe: str

    signal: str
    direction: str
    setup_quality: str
    confidence: int

    entry_price: Decimal
    entry_zone_low: Decimal
    entry_zone_high: Decimal

    stop_loss: Decimal

    take_profit_1: Decimal
    take_profit_2: Decimal

    position_size: Decimal
    position_value: Decimal
    required_margin: Decimal
    margin_usage_percent: Decimal
    leverage: Decimal

    risk_reward_1: Decimal
    risk_reward_2: Decimal

    risk_percent: Decimal
    risk_amount: Decimal

    daily_loss_amount: Decimal
    daily_loss_percent: Decimal

    total_exposure_amount: Decimal
    total_exposure_percent: Decimal

    projected_total_exposure_amount: Decimal
    projected_total_exposure_percent: Decimal

    rejection_reasons: list[str]
    warnings: list[str]


def _decimal(value) -> Decimal:
    """
    Safely convert a numeric value to Decimal.
    """
    try:
        result = Decimal(str(value))

        if not result.is_finite():
            raise InvalidOperation

        return result

    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(
            f"Invalid numeric value: {value!r}"
        )


def _zero_decision(
    setup: TradeSetup,
    leverage: Decimal,
    risk_percent: Decimal,
    daily_loss_amount: Decimal,
    total_exposure_amount: Decimal,
    rejection_reasons: list[str],
    warnings: list[str],
) -> ExecutionDecision:
    """
    Build a safe blocked execution decision.

    This is used whenever the setup cannot be safely evaluated.
    """

    zero = Decimal("0.00")

    return ExecutionDecision(
        execution_allowed=False,

        symbol=setup.symbol,
        timeframe=setup.timeframe,

        signal=setup.signal,
        direction=setup.direction,
        setup_quality=setup.setup_quality,
        confidence=setup.confidence,

        entry_price=zero,
        entry_zone_low=zero,
        entry_zone_high=zero,

        stop_loss=zero,

        take_profit_1=zero,
        take_profit_2=zero,

        position_size=zero,
        position_value=zero,
        required_margin=zero,
        margin_usage_percent=zero,
        leverage=leverage,

        risk_reward_1=zero,
        risk_reward_2=zero,

        risk_percent=risk_percent,
        risk_amount=zero,

        daily_loss_amount=daily_loss_amount,
        daily_loss_percent=zero,

        total_exposure_amount=total_exposure_amount,
        total_exposure_percent=zero,

        projected_total_exposure_amount=total_exposure_amount,
        projected_total_exposure_percent=zero,

        rejection_reasons=rejection_reasons,
        warnings=warnings,
    )


def evaluate_execution_gate(
    setup: TradeSetup,
    account_balance: Decimal,
    available_balance: Decimal,
    daily_loss_amount: Decimal = Decimal("0.00"),
    total_exposure_amount: Decimal = Decimal("0.00"),
    risk_percent: Decimal = DEFAULT_EXECUTION_RISK_PERCENT,
    leverage: Decimal = DEFAULT_EXECUTION_LEVERAGE,
) -> ExecutionDecision:

    rejection_reasons: list[str] = []
    warnings: list[str] = []

    # ---------------------------------------------------------
    # NORMALIZE ACCOUNT / RISK VALUES
    # ---------------------------------------------------------

    try:
        account_balance = _decimal(account_balance)
        available_balance = _decimal(available_balance)
        daily_loss_amount = _decimal(daily_loss_amount)
        total_exposure_amount = _decimal(total_exposure_amount)
        risk_percent = _decimal(risk_percent)
        leverage = _decimal(leverage)

    except ValueError as exc:

        rejection_reasons.append(
            f"Execution risk parameters are invalid: {exc}"
        )

        return _zero_decision(
            setup=setup,
            leverage=Decimal("0.00"),
            risk_percent=Decimal("0.00"),
            daily_loss_amount=Decimal("0.00"),
            total_exposure_amount=Decimal("0.00"),
            rejection_reasons=rejection_reasons,
            warnings=warnings,
        )

    # ---------------------------------------------------------
    # BASIC EXECUTION GATE VALIDATION
    # ---------------------------------------------------------

    if setup.signal not in {"long", "short"}:
        rejection_reasons.append(
            "Trade setup does not contain an executable long or short signal"
        )

    if setup.direction not in {"long", "short"}:
        rejection_reasons.append(
            "Trade setup direction is not executable"
        )

    if setup.setup_quality not in APPROVED_SETUP_QUALITIES:
        rejection_reasons.append(
            "Setup quality must be good or high for execution"
        )

    if setup.confidence < MIN_EXECUTION_CONFIDENCE:
        rejection_reasons.append(
            f"Setup confidence is below the execution threshold of "
            f"{MIN_EXECUTION_CONFIDENCE}"
        )

    if setup.warnings:
        warnings.extend(setup.warnings)

    # ---------------------------------------------------------
    # NON-EXECUTABLE SETUP
    #
    # IMPORTANT:
    # Do not send an invalid/no-trade setup into the risk engine.
    # ---------------------------------------------------------

    if rejection_reasons:

        return _zero_decision(
            setup=setup,
            leverage=leverage,
            risk_percent=risk_percent,
            daily_loss_amount=daily_loss_amount,
            total_exposure_amount=total_exposure_amount,
            rejection_reasons=rejection_reasons,
            warnings=warnings,
        )

    # ---------------------------------------------------------
    # VALIDATE AND CONVERT TRADE PRICES
    # ---------------------------------------------------------

    try:
        entry_price = _decimal(setup.entry_price)
        entry_zone_low = _decimal(setup.entry_zone_low)
        entry_zone_high = _decimal(setup.entry_zone_high)

        stop_loss = _decimal(setup.stop_loss)

        take_profit_1 = _decimal(setup.take_profit_1)
        take_profit_2 = _decimal(setup.take_profit_2)

    except ValueError as exc:

        rejection_reasons.append(
            "Trade setup contains invalid price data and cannot be evaluated for execution"
        )

        warnings.append(str(exc))

        return _zero_decision(
            setup=setup,
            leverage=leverage,
            risk_percent=risk_percent,
            daily_loss_amount=daily_loss_amount,
            total_exposure_amount=total_exposure_amount,
            rejection_reasons=rejection_reasons,
            warnings=warnings,
        )

    # ---------------------------------------------------------
    # BASIC PRICE SANITY CHECK
    # ---------------------------------------------------------

    if (
        entry_price <= 0
        or entry_zone_low <= 0
        or entry_zone_high <= 0
        or stop_loss <= 0
        or take_profit_1 <= 0
        or take_profit_2 <= 0
    ):

        rejection_reasons.append(
            "Trade setup contains non-positive price values"
        )

        return _zero_decision(
            setup=setup,
            leverage=leverage,
            risk_percent=risk_percent,
            daily_loss_amount=daily_loss_amount,
            total_exposure_amount=total_exposure_amount,
            rejection_reasons=rejection_reasons,
            warnings=warnings,
        )

    # ---------------------------------------------------------
    # EXECUTION DIRECTION CONSISTENCY
    # ---------------------------------------------------------

    if setup.signal != setup.direction:

        rejection_reasons.append(
            "Trade setup signal and direction do not match"
        )

    # ---------------------------------------------------------
    # RISK MANAGEMENT
    # ---------------------------------------------------------

    risk_assessment = assess_risk(
        account_balance=account_balance,
        available_balance=available_balance,

        entry_price=entry_price,
        stop_loss=stop_loss,

        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,

        risk_percent=risk_percent,

        daily_loss_amount=daily_loss_amount,
        total_exposure_amount=total_exposure_amount,

        leverage=leverage,

        direction=setup.direction,
    )

    # ---------------------------------------------------------
    # RISK REJECTION
    # ---------------------------------------------------------

    if not risk_assessment.approved:

        rejection_reasons.extend(
            risk_assessment.rejection_reasons
        )

    warnings.extend(
        risk_assessment.warnings
    )

    # ---------------------------------------------------------
    # FINAL EXECUTION DECISION
    # ---------------------------------------------------------

    execution_allowed = (
        len(rejection_reasons) == 0
    )

    return ExecutionDecision(
        execution_allowed=execution_allowed,

        symbol=setup.symbol,
        timeframe=setup.timeframe,

        signal=setup.signal,
        direction=setup.direction,
        setup_quality=setup.setup_quality,
        confidence=setup.confidence,

        entry_price=entry_price,

        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,

        stop_loss=stop_loss,

        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,

        position_size=risk_assessment.position_size,
        position_value=risk_assessment.position_value,

        required_margin=risk_assessment.required_margin,
        margin_usage_percent=risk_assessment.margin_usage_percent,

        leverage=risk_assessment.leverage,

        risk_reward_1=risk_assessment.risk_reward_1,
        risk_reward_2=risk_assessment.risk_reward_2,

        risk_percent=risk_assessment.risk_percent,
        risk_amount=risk_assessment.risk_amount,

        daily_loss_amount=risk_assessment.daily_loss_amount,
        daily_loss_percent=risk_assessment.daily_loss_percent,

        total_exposure_amount=risk_assessment.total_exposure_amount,
        total_exposure_percent=risk_assessment.total_exposure_percent,

        projected_total_exposure_amount=(
            risk_assessment.projected_total_exposure_amount
        ),

        projected_total_exposure_percent=(
            risk_assessment.projected_total_exposure_percent
        ),

        rejection_reasons=rejection_reasons,
        warnings=warnings,
    )


def serialize_execution_decision(
    decision: ExecutionDecision,
) -> dict:

    return {
        "execution_allowed": decision.execution_allowed,

        "symbol": decision.symbol,
        "timeframe": decision.timeframe,

        "signal": decision.signal,
        "direction": decision.direction,

        "setup_quality": decision.setup_quality,
        "confidence": decision.confidence,

        "entry_price": decision.entry_price,

        "entry_zone": {
            "low": decision.entry_zone_low,
            "high": decision.entry_zone_high,
        },

        "stop_loss": decision.stop_loss,

        "take_profit_1": decision.take_profit_1,
        "take_profit_2": decision.take_profit_2,

        "position_size": decision.position_size,
        "position_value": decision.position_value,

        "required_margin": decision.required_margin,
        "margin_usage_percent": decision.margin_usage_percent,

        "leverage": decision.leverage,

        "risk_reward_1": decision.risk_reward_1,
        "risk_reward_2": decision.risk_reward_2,

        "risk_percent": decision.risk_percent,
        "risk_amount": decision.risk_amount,

        "daily_loss_amount": decision.daily_loss_amount,
        "daily_loss_percent": decision.daily_loss_percent,

        "total_exposure_amount": decision.total_exposure_amount,
        "total_exposure_percent": decision.total_exposure_percent,

        "projected_total_exposure_amount": (
            decision.projected_total_exposure_amount
        ),

        "projected_total_exposure_percent": (
            decision.projected_total_exposure_percent
        ),

        "rejection_reasons": decision.rejection_reasons,
        "warnings": decision.warnings,
    }