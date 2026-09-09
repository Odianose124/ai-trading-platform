from decimal import Decimal

from app.database.connection import SessionLocal
from app.models.trade_intent import TradeIntent
from app.services.revalidation_intent_service import (
    revalidation_intent_service,
)


def main():
    print("=" * 70)
    print("SAFE REVALIDATION → NEW TRADE INTENT TEST")
    print("=" * 70)

    db = SessionLocal()

    try:
        # Find the latest pending, unexecuted intent for user 4.
        original = (
            db.query(TradeIntent)
            .filter(
                TradeIntent.user_id == 4,
                TradeIntent.confirmation_status == "pending",
                TradeIntent.execution_status == "not_executed",
            )
            .order_by(TradeIntent.id.desc())
            .first()
        )

        if original is None:
            print("ERROR: No pending trade intent is available for testing.")
            print("Create a fresh trade intent first.")
            return

        original_id = original.id

        # Capture the original values before revalidation.
        original_values = {
            "signal_entry_price": original.signal_entry_price,
            "execution_price": original.execution_price,
            "stop_loss": original.stop_loss,
            "take_profit": original.take_profit,
            "volume": original.volume,
            "confirmation_status": original.confirmation_status,
            "execution_status": original.execution_status,
        }

        print()
        print("ORIGINAL INTENT")
        print("-" * 70)
        print(f"Intent ID:              {original_id}")
        print(f"Symbol:                 {original.symbol}")
        print(f"Broker symbol:          {original.broker_symbol}")
        print(f"Direction:              {original.direction}")
        print(f"Signal entry:           {original.signal_entry_price}")
        print(f"Execution price:        {original.execution_price}")
        print(f"Stop loss:              {original.stop_loss}")
        print(f"Take profit:            {original.take_profit}")
        print(f"Volume:                 {original.volume}")
        print(f"Confirmation status:    {original.confirmation_status}")
        print(f"Execution status:       {original.execution_status}")

        print()
        print("Running fresh revalidation...")
        print("Real MT5 order_send() must NOT be called.")
        print()

        result = revalidation_intent_service.revalidate_and_create(
            db=db,
            intent_id=original_id,
            user_id=4,
        )

        data = result.serialize()

        print("=" * 70)
        print("REVALIDATION RESULT")
        print("=" * 70)

        for key, value in data.items():
            print(f"{key}: {value}")

        if not result.approved:
            print()
            print("=" * 70)
            print("REVALIDATION DID NOT CREATE A NEW INTENT")
            print("=" * 70)
            print("This is not necessarily a failure.")
            print("Fresh market conditions may have invalidated the setup.")
            return

        new_intent_id = result.new_intent_id

        if new_intent_id is None:
            print()
            print("FAIL: Revalidation reported success but returned no new intent ID.")
            return

        print()
        print("=" * 70)
        print("VERIFYING NEW INTENT")
        print("=" * 70)

        new_intent = (
            db.query(TradeIntent)
            .filter(
                TradeIntent.id == new_intent_id,
                TradeIntent.user_id == 4,
            )
            .first()
        )

        if new_intent is None:
            print("FAIL: New trade intent was not found in database.")
            return

        print(f"New intent ID:          {new_intent.id}")
        print(f"Symbol:                 {new_intent.symbol}")
        print(f"Broker symbol:          {new_intent.broker_symbol}")
        print(f"Direction:              {new_intent.direction}")
        print(f"Signal entry:           {new_intent.signal_entry_price}")
        print(f"Execution price:        {new_intent.execution_price}")
        print(f"Stop loss:              {new_intent.stop_loss}")
        print(f"Take profit:            {new_intent.take_profit}")
        print(f"Volume:                 {new_intent.volume}")
        print(f"Risk percent:           {new_intent.risk_percent}")
        print(f"Confirmation status:    {new_intent.confirmation_status}")
        print(f"Execution status:       {new_intent.execution_status}")
        print(f"Expires at:             {new_intent.expires_at}")

        print()
        print("=" * 70)
        print("SAFETY CHECKS")
        print("=" * 70)

        # 1. New intent must be different.
        if new_intent.id == original_id:
            print("FAIL: Revalidation reused the original intent ID.")
            return

        print("PASS: A NEW trade intent was created.")

        # 2. Original values must remain unchanged.
        db.refresh(original)

        unchanged = (
            original.signal_entry_price
            == original_values["signal_entry_price"]
            and original.execution_price
            == original_values["execution_price"]
            and original.stop_loss
            == original_values["stop_loss"]
            and original.take_profit
            == original_values["take_profit"]
            and original.volume
            == original_values["volume"]
            and original.confirmation_status
            == original_values["confirmation_status"]
            and original.execution_status
            == original_values["execution_status"]
        )

        if not unchanged:
            print("FAIL: Original intent was modified.")
            return

        print("PASS: Original trade intent remains unchanged.")

        # 3. New intent must be pending.
        if new_intent.confirmation_status != "pending":
            print(
                "FAIL: New intent is not pending confirmation."
            )
            return

        print("PASS: New intent is pending confirmation.")

        # 4. New intent must not have executed.
        if new_intent.execution_status != "not_executed":
            print(
                "FAIL: New intent execution status is not "
                "'not_executed'."
            )
            return

        print("PASS: New intent has not been executed.")

        # 5. Validate basic trade geometry.
        if new_intent.direction == "buy":
            geometry_valid = (
                new_intent.stop_loss
                < new_intent.execution_price
                < new_intent.take_profit
            )
        else:
            geometry_valid = (
                new_intent.stop_loss
                > new_intent.execution_price
                > new_intent.take_profit
            )

        if not geometry_valid:
            print("FAIL: New intent trade geometry is invalid.")
            return

        print("PASS: New intent trade geometry is valid.")

        # 6. Ensure there is no execution ticket.
        if (
            new_intent.order_ticket is not None
            or new_intent.deal_ticket is not None
        ):
            print("FAIL: New intent contains an execution ticket.")
            return

        print("PASS: No MT5 order/deal ticket was recorded.")

        # 7. Confirm original intent was not executed.
        if original.execution_status != "not_executed":
            print("FAIL: Original intent execution status changed.")
            return

        print("PASS: Original intent was not executed.")

        print()
        print("=" * 70)
        print("FINAL SAFETY RESULT")
        print("=" * 70)
        print("PASS: Revalidation created a separate executable intent.")
        print("PASS: Original intent was preserved.")
        print("PASS: New intent requires explicit confirmation.")
        print("PASS: New intent has not been executed.")
        print("PASS: No MT5 order was sent.")
        print()
        print("REVALIDATION → NEW INTENT TEST COMPLETE")
        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    main()