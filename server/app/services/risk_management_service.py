from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


DEFAULT_RISK_PERCENT = Decimal("1.00")
MAX_RISK_PERCENT = Decimal("2.00")

MIN_RISK_REWARD = Decimal("1.50")

MAX_DAILY_LOSS_PERCENT = Decimal("5.00")

# Maximum gross notional exposure allowed by the platform.
# 10x account balance is a conservative gross-exposure ceiling.
MAX_TOTAL_EXPOSURE_MULTIPLE = Decimal("10.00")
MAX_TOTAL_EXPOSURE_PERCENT = MAX_TOTAL_EXPOSURE_MULTIPLE * Decimal("100")

DEFAULT_LEVERAGE = Decimal("1.00")

MIN_POSITION_SIZE = Decimal("0.00000001")


@dataclass
class RiskAssessment:
    approved: bool

    account_balance: Decimal
    available_balance: Decimal

    risk_percent: Decimal
    risk_amount: Decimal

    leverage: Decimal

    entry_price: Decimal
    stop_loss: Decimal

    stop_distance: Decimal
    stop_distance_percent: Decimal

    position_size: Decimal
    position_value: Decimal

    required_margin: Decimal
    margin_usage_percent: Decimal

    take_profit_1: Decimal
    take_profit_2: Decimal

    risk_reward_1: Decimal
    risk_reward_2: Decimal

    daily_loss_amount: Decimal
    daily_loss_percent: Decimal

    total_exposure_amount: Decimal
    total_exposure_percent: Decimal

    projected_total_exposure_amount: Decimal
    projected_total_exposure_percent: Decimal

    rejection_reasons: list[str]
    warnings: list[str]


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _percent(value: Decimal) -> Decimal:
    return Decimal(value).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _quantity(value: Decimal) -> Decimal:
    return Decimal(value).quantize(
        Decimal("0.00000001"),
        rounding=ROUND_HALF_UP,
    )


def calculate_risk_amount(
    account_balance: Decimal,
    risk_percent: Decimal,
) -> Decimal:
    return _money(
        account_balance * risk_percent / Decimal("100")
    )


def calculate_stop_distance(
    entry_price: Decimal,
    stop_loss: Decimal,
) -> Decimal:
    return abs(entry_price - stop_loss)


def calculate_stop_distance_percent(
    entry_price: Decimal,
    stop_loss: Decimal,
) -> Decimal:
    if entry_price <= 0:
        return Decimal("0.00")

    distance = calculate_stop_distance(
        entry_price,
        stop_loss,
    )

    return _percent(
        distance / entry_price * Decimal("100")
    )


def calculate_position_size(
    risk_amount: Decimal,
    stop_distance: Decimal,
) -> Decimal:
    if stop_distance <= 0:
        return Decimal("0.00000000")

    return _quantity(
        risk_amount / stop_distance
    )


def calculate_position_value(
    position_size: Decimal,
    entry_price: Decimal,
) -> Decimal:
    return _money(
        position_size * entry_price
    )


def calculate_required_margin(
    position_value: Decimal,
    leverage: Decimal,
) -> Decimal:
    if leverage <= 0:
        return Decimal("0.00")

    return _money(
        position_value / leverage
    )


def calculate_margin_usage_percent(
    required_margin: Decimal,
    available_balance: Decimal,
) -> Decimal:
    if available_balance <= 0:
        return Decimal("100.00")

    return _percent(
        required_margin / available_balance * Decimal("100")
    )


def calculate_risk_reward(
    entry_price: Decimal,
    stop_loss: Decimal,
    take_profit: Decimal,
) -> Decimal:
    risk = abs(entry_price - stop_loss)
    reward = abs(take_profit - entry_price)

    if risk <= 0:
        return Decimal("0.00")

    return _percent(
        reward / risk
    )


def assess_risk(
    account_balance: Decimal,
    available_balance: Decimal,
    entry_price: Decimal,
    stop_loss: Decimal,
    take_profit_1: Decimal,
    take_profit_2: Decimal,
    risk_percent: Decimal = DEFAULT_RISK_PERCENT,
    daily_loss_amount: Decimal = Decimal("0.00"),
    total_exposure_amount: Decimal = Decimal("0.00"),
    leverage: Decimal = DEFAULT_LEVERAGE,
    direction: str = "long",
) -> RiskAssessment:

    account_balance = Decimal(str(account_balance))
    available_balance = Decimal(str(available_balance))
    entry_price = Decimal(str(entry_price))
    stop_loss = Decimal(str(stop_loss))
    take_profit_1 = Decimal(str(take_profit_1))
    take_profit_2 = Decimal(str(take_profit_2))
    risk_percent = Decimal(str(risk_percent))
    daily_loss_amount = Decimal(str(daily_loss_amount))
    total_exposure_amount = Decimal(str(total_exposure_amount))
    leverage = Decimal(str(leverage))

    rejection_reasons: list[str] = []
    warnings: list[str] = []

    direction = direction.strip().lower()

    # ---------------------------------------------------------
    # Basic validation
    # ---------------------------------------------------------

    if account_balance <= 0:
        rejection_reasons.append(
            "Trading account balance must be greater than zero"
        )

    if available_balance < 0:
        rejection_reasons.append(
            "Available balance cannot be negative"
        )

    if entry_price <= 0:
        rejection_reasons.append(
            "Entry price must be greater than zero"
        )

    if stop_loss <= 0:
        rejection_reasons.append(
            "Stop loss must be greater than zero"
        )

    if take_profit_1 <= 0:
        rejection_reasons.append(
            "Take profit 1 must be greater than zero"
        )

    if take_profit_2 <= 0:
        rejection_reasons.append(
            "Take profit 2 must be greater than zero"
        )

    if risk_percent <= 0:
        rejection_reasons.append(
            "Risk percentage must be greater than zero"
        )

    if risk_percent > MAX_RISK_PERCENT:
        rejection_reasons.append(
            f"Risk percentage cannot exceed {MAX_RISK_PERCENT}%"
        )

    if leverage <= 0:
        rejection_reasons.append(
            "Leverage must be greater than zero"
        )

    # ---------------------------------------------------------
    # Direction validation
    # ---------------------------------------------------------

    if direction not in {"long", "short"}:
        rejection_reasons.append(
            "Direction must be either long or short"
        )

    if direction == "long":
        if stop_loss >= entry_price:
            rejection_reasons.append(
                "For a long trade, stop loss must be below entry price"
            )

        if take_profit_1 <= entry_price:
            rejection_reasons.append(
                "For a long trade, take profit 1 must be above entry price"
            )

        if take_profit_2 <= entry_price:
            rejection_reasons.append(
                "For a long trade, take profit 2 must be above entry price"
            )

    elif direction == "short":
        if stop_loss <= entry_price:
            rejection_reasons.append(
                "For a short trade, stop loss must be above entry price"
            )

        if take_profit_1 >= entry_price:
            rejection_reasons.append(
                "For a short trade, take profit 1 must be below entry price"
            )

        if take_profit_2 >= entry_price:
            rejection_reasons.append(
                "For a short trade, take profit 2 must be below entry price"
            )

    # ---------------------------------------------------------
    # Risk calculations
    # ---------------------------------------------------------

    risk_amount = calculate_risk_amount(
        account_balance,
        risk_percent,
    )

    stop_distance = calculate_stop_distance(
        entry_price,
        stop_loss,
    )

    stop_distance_percent = calculate_stop_distance_percent(
        entry_price,
        stop_loss,
    )

    position_size = calculate_position_size(
        risk_amount,
        stop_distance,
    )

    position_value = calculate_position_value(
        position_size,
        entry_price,
    )

    required_margin = calculate_required_margin(
        position_value,
        leverage,
    )

    margin_usage_percent = calculate_margin_usage_percent(
        required_margin,
        available_balance,
    )

    risk_reward_1 = calculate_risk_reward(
        entry_price,
        stop_loss,
        take_profit_1,
    )

    risk_reward_2 = calculate_risk_reward(
        entry_price,
        stop_loss,
        take_profit_2,
    )

    # ---------------------------------------------------------
    # Daily loss
    # ---------------------------------------------------------

    if account_balance > 0:
        daily_loss_percent = _percent(
            daily_loss_amount
            / account_balance
            * Decimal("100")
        )
    else:
        daily_loss_percent = Decimal("100.00")

    if daily_loss_percent >= MAX_DAILY_LOSS_PERCENT:
        rejection_reasons.append(
            f"Daily loss limit of {MAX_DAILY_LOSS_PERCENT}% has been reached"
        )

    # ---------------------------------------------------------
    # Risk amount validation
    # ---------------------------------------------------------

    if risk_amount > available_balance:
        rejection_reasons.append(
            "Calculated risk amount exceeds available balance"
        )

    # ---------------------------------------------------------
    # Position size validation
    # ---------------------------------------------------------

    if position_size < MIN_POSITION_SIZE:
        rejection_reasons.append(
            "Calculated position size is below the minimum supported size"
        )

    # ---------------------------------------------------------
    # Risk/reward validation
    # ---------------------------------------------------------

    if risk_reward_1 < MIN_RISK_REWARD:
        rejection_reasons.append(
            f"Take profit 1 provides less than the minimum "
            f"{MIN_RISK_REWARD}:1 risk/reward ratio"
        )

    # ---------------------------------------------------------
    # Margin validation
    # ---------------------------------------------------------

    if required_margin > available_balance:
        rejection_reasons.append(
            "Required margin exceeds available balance"
        )

    elif margin_usage_percent >= Decimal("80.00"):
        warnings.append(
            "Required margin would consume at least 80% "
            "of the available balance"
        )

    # ---------------------------------------------------------
    # Gross exposure validation
    # ---------------------------------------------------------

    projected_total_exposure_amount = (
        total_exposure_amount + position_value
    )

    if account_balance > 0:
        total_exposure_percent = _percent(
            total_exposure_amount
            / account_balance
            * Decimal("100")
        )

        projected_total_exposure_percent = _percent(
            projected_total_exposure_amount
            / account_balance
            * Decimal("100")
        )
    else:
        total_exposure_percent = Decimal("100.00")
        projected_total_exposure_percent = Decimal("100.00")

    if (
        projected_total_exposure_percent
        > MAX_TOTAL_EXPOSURE_PERCENT
    ):
        rejection_reasons.append(
            f"Projected gross exposure would exceed "
            f"the {MAX_TOTAL_EXPOSURE_MULTIPLE}x account exposure limit"
        )

    # ---------------------------------------------------------
    # Stop-distance warning
    # ---------------------------------------------------------

    if stop_distance_percent >= Decimal("5.00"):
        warnings.append(
            "Stop-loss distance is at least 5% from entry"
        )

    # ---------------------------------------------------------
    # Leverage information
    # ---------------------------------------------------------

    if leverage == Decimal("1.00"):
        warnings.append(
            "No leverage is applied; the position must be fully margined"
        )

    # ---------------------------------------------------------
    # Final approval
    # ---------------------------------------------------------

    approved = len(rejection_reasons) == 0

    return RiskAssessment(
        approved=approved,

        account_balance=_money(account_balance),
        available_balance=_money(available_balance),

        risk_percent=_percent(risk_percent),
        risk_amount=risk_amount,

        leverage=leverage,

        entry_price=entry_price,
        stop_loss=stop_loss,

        stop_distance=_money(stop_distance),
        stop_distance_percent=stop_distance_percent,

        position_size=position_size,
        position_value=position_value,

        required_margin=required_margin,
        margin_usage_percent=margin_usage_percent,

        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,

        risk_reward_1=risk_reward_1,
        risk_reward_2=risk_reward_2,

        daily_loss_amount=_money(daily_loss_amount),
        daily_loss_percent=daily_loss_percent,

        total_exposure_amount=_money(
            total_exposure_amount
        ),
        total_exposure_percent=total_exposure_percent,

        projected_total_exposure_amount=_money(
            projected_total_exposure_amount
        ),
        projected_total_exposure_percent=(
            projected_total_exposure_percent
        ),

        rejection_reasons=rejection_reasons,
        warnings=warnings,
    )


def serialize_risk_assessment(
    assessment: RiskAssessment,
) -> dict:

    return {
        "approved": assessment.approved,

        "account_balance": assessment.account_balance,
        "available_balance": assessment.available_balance,

        "risk_percent": assessment.risk_percent,
        "risk_amount": assessment.risk_amount,

        "leverage": assessment.leverage,

        "entry_price": assessment.entry_price,
        "stop_loss": assessment.stop_loss,

        "stop_distance": assessment.stop_distance,
        "stop_distance_percent": (
            assessment.stop_distance_percent
        ),

        "position_size": assessment.position_size,
        "position_value": assessment.position_value,

        "required_margin": assessment.required_margin,
        "margin_usage_percent": (
            assessment.margin_usage_percent
        ),

        "take_profit_1": assessment.take_profit_1,
        "take_profit_2": assessment.take_profit_2,

        "risk_reward_1": assessment.risk_reward_1,
        "risk_reward_2": assessment.risk_reward_2,

        "daily_loss_amount": assessment.daily_loss_amount,
        "daily_loss_percent": assessment.daily_loss_percent,

        "total_exposure_amount": (
            assessment.total_exposure_amount
        ),
        "total_exposure_percent": (
            assessment.total_exposure_percent
        ),

        "projected_total_exposure_amount": (
            assessment.projected_total_exposure_amount
        ),
        "projected_total_exposure_percent": (
            assessment.projected_total_exposure_percent
        ),

        "rejection_reasons": assessment.rejection_reasons,
        "warnings": assessment.warnings,
    }