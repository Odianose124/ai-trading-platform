from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.connection import Base
from app.models.trade_intent import TradeIntent
from app.services import trade_confirmation_service as confirmation_module


DATABASE_URL = "sqlite:///./ai_trading.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

TestSessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def create_test_intent():
    db = TestSessionLocal()

    try:
        now = datetime.now(timezone.utc)

        intent = TradeIntent(
            user_id=4,
            symbol="BTCUSD",
            broker_symbol="BTCUSDm",
            direction="buy",
            volume=Decimal("0.01"),
            signal_entry_price=Decimal("79690.87"),
            execution_price=Decimal("79690.87"),
            stop_loss=Decimal("79479.19"),
            take_profit=Decimal("80008.39"),
            risk_percent=Decimal("1.00"),
            preview_status="approved",
            confirmation_status="pending",
            execution_status="not_executed",
            signal_price_deviation_percent=Decimal("0"),
            margin_required=Decimal("8.00"),
            free_margin=Decimal("964.97"),
            expires_at=now + timedelta(minutes=5),
            created_at=now,
            updated_at=now,
        )

        db.add(intent)
        db.commit()
        db.refresh(intent)

        print(f"Created test intent: {intent.id}")

        return intent.id

    finally:
        db.close()


class FakeExecutionResult:
    approved = True
    execution_sent = False
    order_ticket = None
    deal_ticket = None
    retcode = None
    retcode_description = None
    risk_amount = Decimal("0")
    signal_price_deviation = Decimal("0")
    signal_price_deviation_percent = Decimal("0")
    checks = [
        "FAKE execution service reached",
    ]
    warnings = []
    errors = []
    message = (
        "Fake execution service used. "
        "No MT5 order was sent."
    )


def fake_execute(*args, **kwargs):
    print(
        "WARNING: fake_execute() was called. "
        "NO MT5 order was sent."
    )

    return FakeExecutionResult()


def confirm_intent(intent_id):
    db = TestSessionLocal()

    try:
        result = confirmation_module.trade_confirmation_service.confirm(
            db=db,
            intent_id=intent_id,
            user_id=4,
        )

        return result.serialize()

    except Exception as exc:
        return {
            "exception": type(exc).__name__,
            "message": str(exc),
        }

    finally:
        db.close()


def main():
    print("=" * 70)
    print("SAFE TRADE CONFIRMATION ATOMIC-CLAIM TEST")
    print("=" * 70)

    print()
    print("Installing fake execution service...")
    print("Real MT5 order_send() will NOT be called.")

    original_execute = (
        confirmation_module.mt5_execution_service.execute
    )

    confirmation_module.mt5_execution_service.execute = fake_execute

    try:
        intent_id = create_test_intent()

        print()
        print(f"Testing intent ID: {intent_id}")
        print("Starting two confirmation requests concurrently...")
        print()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    confirm_intent,
                    intent_id,
                ),
                executor.submit(
                    confirm_intent,
                    intent_id,
                ),
            ]

            results = [
                future.result()
                for future in futures
            ]

        print()
        print("=" * 70)
        print("RESULTS")
        print("=" * 70)

        for index, result in enumerate(results, start=1):
            print()
            print(f"REQUEST {index}")
            print("-" * 70)

            for key, value in result.items():
                print(f"{key}: {value}")

        db = TestSessionLocal()

        try:
            intent = (
                db.query(TradeIntent)
                .filter(
                    TradeIntent.id == intent_id
                )
                .first()
            )

            print()
            print("=" * 70)
            print("FINAL DATABASE STATE")
            print("=" * 70)

            if intent is None:
                print("ERROR: Test intent was not found.")
                return

            print(f"Intent ID: {intent.id}")
            print(
                "Confirmation status: "
                f"{intent.confirmation_status}"
            )
            print(
                "Execution status: "
                f"{intent.execution_status}"
            )
            print(
                "Order ticket: "
                f"{intent.order_ticket}"
            )
            print(
                "Deal ticket: "
                f"{intent.deal_ticket}"
            )

            print()
            print("=" * 70)
            print("SAFETY CHECK")
            print("=" * 70)

            statuses = [
                result.get("status")
                for result in results
            ]

            print(f"Confirmation statuses: {statuses}")

            if "already_processed" not in statuses:
                print(
                    "FAIL: No request returned "
                    "'already_processed'."
                )
                return

            already_processed_count = statuses.count(
                "already_processed"
            )

            if already_processed_count != 1:
                print(
                    "FAIL: Expected exactly one "
                    "'already_processed' result."
                )
                return

            print(
                "PASS: Exactly one confirmation request "
                "was rejected as already processed."
            )

            print()
            print(
                "PASS: Atomic replay protection is working."
            )

            print(
                "PASS: The same intent could not be "
                "claimed twice."
            )

            print(
                "PASS: The real MT5 execution service "
                "was not used."
            )

            print(
                "PASS: No MT5 order was sent."
            )

        finally:
            db.close()

    finally:
        confirmation_module.mt5_execution_service.execute = (
            original_execute
        )

    print()
    print("=" * 70)
    print("SAFE TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()