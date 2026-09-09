from decimal import Decimal

from app.services.execution_gate_service import (
    evaluate_execution_gate,
)


class MockSetup:
    symbol = "BTCUSD"
    timeframe = "15m"

    signal = "short"
    direction = "short"
    setup_quality = "high"
    confidence = 82

    entry_price = Decimal("77894.75")
    entry_zone_low = Decimal("77894.75")
    entry_zone_high = Decimal("78194.14")

    stop_loss = Decimal("78224.08")
    take_profit_1 = Decimal("77400.76")
    take_profit_2 = Decimal("77071.43")

    risk_reward_1 = Decimal("1.50")
    risk_reward_2 = Decimal("2.50")

    warnings = []


setup = MockSetup()

decision = evaluate_execution_gate(
    setup=setup,
    account_balance=Decimal("10000.00"),
    available_balance=Decimal("10000.00"),
    daily_loss_amount=Decimal("100.00"),
    total_exposure_amount=Decimal("0.00"),
    risk_percent=Decimal("1.00"),
)

print("EXECUTION GATE TEST")
print("-------------------")
print("Execution allowed:", decision.execution_allowed)
print("Symbol:", decision.symbol)
print("Timeframe:", decision.timeframe)
print("Signal:", decision.signal)
print("Direction:", decision.direction)
print("Setup quality:", decision.setup_quality)
print("Confidence:", decision.confidence)
print("Entry:", decision.entry_price)
print("Stop loss:", decision.stop_loss)
print("Take profit 1:", decision.take_profit_1)
print("Take profit 2:", decision.take_profit_2)
print("Position size:", decision.position_size)
print("Risk percent:", decision.risk_percent)
print("Risk amount:", decision.risk_amount)
print("RR1:", decision.risk_reward_1)
print("RR2:", decision.risk_reward_2)
print("Rejections:", decision.rejection_reasons)
print("Warnings:", decision.warnings)
print("-------------------")

assert decision.signal == "short"
assert decision.direction == "short"
assert decision.confidence == 82
assert decision.risk_percent == Decimal("1.00")
assert decision.risk_amount == Decimal("100.00")

print("EXECUTION GATE ENGINE: OK")