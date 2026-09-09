from app.services.trade_revalidation_service import trade_revalidation_service


result = trade_revalidation_service.revalidate(
    intent_id=5,
    symbol="BTCUSD",
    direction="buy",
    original_signal_entry_price="79690.87",
    original_stop_loss="79479.19",
    original_take_profit="80008.39",
    risk_percent="1.00",
    volume="0.01",
    timeframe="15m",
    limit=500,
    strength=2,
    lookback=20,
    minimum_touches=2,
)

print("\n" + "=" * 70)
print("TRADE REVALIDATION TEST")
print("=" * 70)

data = result.serialize()

for key, value in data.items():
    print(f"{key}: {value}")

print("\n" + "=" * 70)
print("SAFETY CHECK")
print("=" * 70)

print("approved:", result.approved)
print("status:", result.status)
print("execution was NOT requested.")
print("No MT5 order should have been sent.")

if result.approved:
    print("\nPASS: Fresh trade setup passed revalidation.")
    print("The returned SL/TP/volume are based on fresh market conditions.")
else:
    print("\nSAFE RESULT: Trade was rejected by revalidation.")
    print("This is acceptable if current market conditions no longer support the setup.")

print("\nREVALIDATION TEST COMPLETE")