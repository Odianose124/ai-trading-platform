from decimal import Decimal

from app.services.risk_management_service import (
    assess_risk,
)


account_balance = Decimal("98.50")

assessment = assess_risk(
    account_balance=account_balance,
    available_balance=account_balance,
    entry_price=Decimal("77894.75"),
    stop_loss=Decimal("78224.08"),
    take_profit_1=Decimal("77400.76"),
    take_profit_2=Decimal("77071.43"),
    risk_percent=Decimal("1.00"),
)

print("RISK MANAGEMENT TEST")
print("--------------------")
print("Approved:", assessment.approved)
print("Account balance:", assessment.account_balance)
print("Risk percent:", assessment.risk_percent)
print("Risk amount:", assessment.risk_amount)
print("Entry:", assessment.entry_price)
print("Stop loss:", assessment.stop_loss)
print("Stop distance:", assessment.stop_distance)
print("Stop distance %:", assessment.stop_distance_percent)
print("Position size:", assessment.position_size)
print("Position value:", assessment.position_value)
print("TP1:", assessment.take_profit_1)
print("TP2:", assessment.take_profit_2)
print("RR1:", assessment.risk_reward_1)
print("RR2:", assessment.risk_reward_2)
print("Rejections:", assessment.rejection_reasons)
print("Warnings:", assessment.warnings)

assert assessment.risk_amount == Decimal("0.99")
assert assessment.position_size > Decimal("0")
assert assessment.risk_reward_1 == Decimal("1.50")
assert assessment.risk_reward_2 == Decimal("2.50")

print("--------------------")
print("RISK MANAGEMENT ENGINE: OK")