from app.database.connection import SessionLocal
from app.models.trade_intent import TradeIntent
from datetime import datetime, timezone, timedelta


db = SessionLocal()

try:
    intent = TradeIntent(
        user_id=4,
        symbol="BTCUSD",
        broker_symbol="BTCUSDm",
        direction="buy",
        volume=0.01,
        signal_entry_price=79690.87,
        execution_price=79690.87,
        stop_loss=79479.19,
        take_profit=80008.39,
        risk_percent=1.0,
        preview_status="ready_for_confirmation",
        confirmation_status="pending",
        execution_status="not_executed",
        signal_price_deviation_percent=0.0,
        margin_required=0.0,
        free_margin=964.97,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
    )

    db.add(intent)
    db.commit()
    db.refresh(intent)

    print("=" * 70)
    print("FRESH PENDING TRADE INTENT CREATED")
    print("=" * 70)
    print()
    print(f"Intent ID:           {intent.id}")
    print(f"User ID:             {intent.user_id}")
    print(f"Symbol:              {intent.symbol}")
    print(f"Broker symbol:       {intent.broker_symbol}")
    print(f"Direction:           {intent.direction}")
    print(f"Volume:              {intent.volume}")
    print(f"Signal entry:        {intent.signal_entry_price}")
    print(f"Execution price:     {intent.execution_price}")
    print(f"Stop loss:           {intent.stop_loss}")
    print(f"Take profit:         {intent.take_profit}")
    print(f"Risk percent:        {intent.risk_percent}")
    print(f"Confirmation status: {intent.confirmation_status}")
    print(f"Execution status:    {intent.execution_status}")
    print(f"Expires at:          {intent.expires_at}")
    print()
    print("This intent is pending confirmation.")
    print("No MT5 order was sent.")
    print("=" * 70)

finally:
    db.close()