from __future__ import annotations

import MetaTrader5 as mt5

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models.mt5_trading_account import MT5TradingAccount
from app.models.trade_intent import TradeIntent
from app.mt5.connection import MT5AccountMismatchError, MT5ConnectionError, mt5_connection
from app.services.position_reconciliation_service import position_reconciliation_service


MAGIC_NUMBER = 202609


@dataclass
class PendingOrderReconciliationResult:
    reconciled: bool
    status: str
    intent_id: int
    order_ticket: int | None
    deal_ticket: int | None
    position_ticket: int | None
    order_state: str | None
    execution_price: Decimal | None
    checks: list[str]
    warnings: list[str]
    errors: list[str]
    message: str

    def serialize(self) -> dict[str, Any]:
        return {
            "reconciled": self.reconciled,
            "status": self.status,
            "intent_id": self.intent_id,
            "order_ticket": self.order_ticket,
            "deal_ticket": self.deal_ticket,
            "position_ticket": self.position_ticket,
            "order_state": self.order_state,
            "execution_price": (
                float(self.execution_price)
                if self.execution_price is not None
                else None
            ),
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "message": self.message,
        }


class PendingOrderReconciliationService:
    """
    Reconciles platform-owned pending MT5 orders.

    Lifecycle:

        pending_order_placed
            -> placed
            -> partial
            -> filled
            -> actual live position
            -> ManagedPosition
            -> executed

    Terminal broker states:

        cancelled
        rejected
        expired

    This service never calls mt5.order_send().
    """

    def __init__(self) -> None:
        self.magic_number = MAGIC_NUMBER

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value is None:
            return None

        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        try:
            return datetime.fromtimestamp(
                int(value),
                tz=timezone.utc,
            )
        except (TypeError, ValueError, OSError):
            return datetime.now(timezone.utc)

    @staticmethod
    def _state_name(state: Any) -> str:
        try:
            numeric_state = int(state)
        except (TypeError, ValueError):
            return "unknown"

        mapping = {
            getattr(mt5, "ORDER_STATE_STARTED", -999): "started",
            getattr(mt5, "ORDER_STATE_PLACED", -998): "placed",
            getattr(mt5, "ORDER_STATE_CANCELED", -997): "cancelled",
            getattr(mt5, "ORDER_STATE_PARTIAL", -996): "partial",
            getattr(mt5, "ORDER_STATE_FILLED", -995): "filled",
            getattr(mt5, "ORDER_STATE_REJECTED", -994): "rejected",
            getattr(mt5, "ORDER_STATE_EXPIRED", -993): "expired",
            getattr(mt5, "ORDER_STATE_REQUEST_ADD", -992): "request_add",
            getattr(mt5, "ORDER_STATE_REQUEST_MODIFY", -991): "request_modify",
            getattr(mt5, "ORDER_STATE_REQUEST_CANCEL", -990): "request_cancel",
        }

        return mapping.get(numeric_state, f"unknown_{numeric_state}")

    def _verify_account(
        self,
        db: Session,
        intent: TradeIntent,
    ) -> MT5TradingAccount:
        account = (
            db.query(MT5TradingAccount)
            .filter(
                MT5TradingAccount.user_id == int(intent.user_id),
                MT5TradingAccount.is_active.is_(True),
            )
            .first()
        )

        if account is None:
            raise RuntimeError(
                "No active MT5 trading account is assigned to the user."
            )

        try:
            mt5_connection.ensure_connected()
            mt5_connection.verify_account(
                expected_login=int(account.mt5_login),
                expected_server=str(account.server),
            )
        except MT5AccountMismatchError as exc:
            raise RuntimeError(
                "Connected MT5 account does not match the user's registered account."
            ) from exc
        except MT5ConnectionError as exc:
            raise RuntimeError(
                f"MT5 connection unavailable: {exc}"
            ) from exc

        return account

    def _get_order(
        self,
        order_ticket: int,
    ) -> Any | None:
        try:
            active_orders = mt5.orders_get(
                ticket=order_ticket
            )
        except Exception:
            active_orders = None

        if active_orders:
            return active_orders[0]

        try:
            history_orders = mt5.history_orders_get(
                ticket=order_ticket
            )
        except Exception:
            history_orders = None

        if history_orders:
            return history_orders[-1]

        return None

    def _get_deals(
        self,
        order_ticket: int,
    ) -> list[Any]:
        try:
            deals = mt5.history_deals_get(
                ticket=order_ticket
            )
        except Exception:
            return []

        return list(deals or [])

    def _find_entry_deal(
        self,
        deals: list[Any],
    ) -> Any | None:
        entry_in = getattr(
            mt5,
            "DEAL_ENTRY_IN",
            0,
        )

        candidates = []

        for deal in deals:
            try:
                magic = int(
                    getattr(deal, "magic", 0) or 0
                )
            except (TypeError, ValueError):
                magic = 0

            if magic != self.magic_number:
                continue

            try:
                entry = int(
                    getattr(deal, "entry", -1)
                )
            except (TypeError, ValueError):
                entry = -1

            if entry != int(entry_in):
                continue

            position_id = getattr(
                deal,
                "position_id",
                None,
            )

            if not position_id:
                continue

            candidates.append(deal)

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: int(
                getattr(item, "time_msc", 0) or 0
            )
        )

        return candidates[-1]

    def _base_result(
        self,
        *,
        intent: TradeIntent,
        status: str,
        order_state: str | None,
        checks: list[str],
        warnings: list[str],
        errors: list[str],
        message: str,
        deal_ticket: int | None = None,
        position_ticket: int | None = None,
        execution_price: Decimal | None = None,
    ) -> PendingOrderReconciliationResult:
        return PendingOrderReconciliationResult(
            reconciled=status == "filled",
            status=status,
            intent_id=int(intent.id),
            order_ticket=(
                int(intent.order_ticket)
                if intent.order_ticket is not None
                else None
            ),
            deal_ticket=deal_ticket,
            position_ticket=position_ticket,
            order_state=order_state,
            execution_price=execution_price,
            checks=checks,
            warnings=warnings,
            errors=errors,
            message=message,
        )

    def reconcile_intent(
        self,
        db: Session,
        *,
        intent_id: int,
        user_id: int,
    ) -> PendingOrderReconciliationResult:
        checks: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []

        intent = (
            db.query(TradeIntent)
            .filter(
                TradeIntent.id == int(intent_id),
                TradeIntent.user_id == int(user_id),
            )
            .first()
        )

        if intent is None:
            return PendingOrderReconciliationResult(
                reconciled=False,
                status="not_found",
                intent_id=int(intent_id),
                order_ticket=None,
                deal_ticket=None,
                position_ticket=None,
                order_state=None,
                execution_price=None,
                checks=[],
                warnings=[],
                errors=["Trade intent was not found."],
                message="Pending trade intent was not found.",
            )

        if (
            getattr(intent, "execution_mode", None)
            != "pending"
        ):
            return self._base_result(
                intent=intent,
                status="not_pending",
                order_state=None,
                checks=[],
                warnings=[],
                errors=[
                    "Trade intent is not a pending-order execution."
                ],
                message="This intent does not represent a pending order.",
            )

        if (
            getattr(intent, "pending_order_status", None)
            in {
                "cancelled",
                "rejected",
                "expired",
                "filled",
            }
            and getattr(intent, "execution_status", None)
            == "executed"
        ):
            return self._base_result(
                intent=intent,
                status="already_reconciled",
                order_state="filled",
                checks=[
                    "Pending order has already been reconciled."
                ],
                warnings=[],
                errors=[],
                message="Pending order has already been fully reconciled.",
                deal_ticket=(
                    int(intent.deal_ticket)
                    if intent.deal_ticket is not None
                    else None
                ),
                position_ticket=(
                    int(intent.filled_position_ticket)
                    if intent.filled_position_ticket is not None
                    else None
                ),
                execution_price=self._decimal(
                    intent.execution_price
                ),
            )

        if intent.order_ticket is None:
            return self._base_result(
                intent=intent,
                status="reconciliation_required",
                order_state=None,
                checks=[],
                warnings=[],
                errors=[
                    "Pending intent has no MT5 order ticket."
                ],
                message="The pending order cannot be reconciled without its MT5 order ticket.",
            )

        try:
            self._verify_account(
                db,
                intent,
            )
        except RuntimeError as exc:
            return self._base_result(
                intent=intent,
                status="reconciliation_required",
                order_state=None,
                checks=[],
                warnings=[],
                errors=[str(exc)],
                message="MT5 ownership could not be verified.",
            )

        checks.append(
            "MT5 account ownership verified."
        )

        order_ticket = int(intent.order_ticket)

        order = self._get_order(
            order_ticket
        )

        if order is None:
            warnings.append(
                "The order is not currently visible in active or historical MT5 orders."
            )

            return self._base_result(
                intent=intent,
                status="reconciliation_required",
                order_state=None,
                checks=checks,
                warnings=warnings,
                errors=[],
                message="Pending order remains unresolved; MT5 returned no order record.",
            )

        try:
            order_magic = int(
                getattr(order, "magic", 0) or 0
            )
        except (TypeError, ValueError):
            order_magic = 0

        if order_magic != self.magic_number:
            return self._base_result(
                intent=intent,
                status="reconciliation_required",
                order_state=None,
                checks=checks,
                warnings=warnings,
                errors=[
                    "MT5 order magic number does not belong to this platform."
                ],
                message="Order ownership validation failed.",
            )

        checks.append(
            "MT5 pending order belongs to the platform magic number."
        )

        order_state = self._state_name(
            getattr(order, "state", None)
        )

        checks.append(
            f"MT5 pending order state resolved as {order_state}."
        )

        deals = self._get_deals(
            order_ticket
        )

        entry_deal = self._find_entry_deal(
            deals
        )

        if order_state in {
            "started",
            "placed",
            "request_add",
            "request_modify",
            "request_cancel",
        }:
            intent.pending_order_status = "placed"
            intent.execution_status = "pending_order_placed"
            intent.updated_at = self._now()
            db.commit()

            return self._base_result(
                intent=intent,
                status="placed",
                order_state=order_state,
                checks=checks,
                warnings=warnings,
                errors=[],
                message="Pending order remains active and is waiting for activation.",
            )

        if order_state == "partial":
            intent.pending_order_status = "partial"
            intent.execution_status = "pending_order_placed"
            intent.updated_at = self._now()
            db.commit()

            return self._base_result(
                intent=intent,
                status="partial",
                order_state=order_state,
                checks=checks,
                warnings=[
                    "MT5 reports a partial pending-order fill. Full reconciliation will wait for the completed fill."
                ],
                errors=[],
                message="Pending order has partially filled and remains active.",
                deal_ticket=(
                    int(entry_deal.ticket)
                    if entry_deal is not None
                    else None
                ),
                position_ticket=(
                    int(entry_deal.position_id)
                    if entry_deal is not None and entry_deal.position_id
                    else None
                ),
                execution_price=(
                    self._decimal(entry_deal.price)
                    if entry_deal is not None
                    else None
                ),
            )

        if order_state in {
            "cancelled",
            "rejected",
            "expired",
        }:
            intent.pending_order_status = order_state
            intent.execution_status = order_state
            intent.confirmation_status = "confirmed"
            intent.error_message = (
                f"MT5 pending order ended with state: {order_state}."
            )
            intent.updated_at = self._now()

            db.commit()

            return self._base_result(
                intent=intent,
                status=order_state,
                order_state=order_state,
                checks=checks,
                warnings=[],
                errors=[],
                message=f"Pending order was {order_state} by MetaTrader 5.",
            )

        if order_state != "filled":
            return self._base_result(
                intent=intent,
                status="reconciliation_required",
                order_state=order_state,
                checks=checks,
                warnings=warnings,
                errors=[
                    f"Unhandled MT5 pending order state: {order_state}."
                ],
                message="Pending order state requires reconciliation review.",
            )

        if entry_deal is None:
            intent.pending_order_status = "filled"
            intent.execution_status = "execution_reconciliation_required"
            intent.updated_at = self._now()
            db.commit()

            return self._base_result(
                intent=intent,
                status="filled",
                order_state=order_state,
                checks=checks,
                warnings=[
                    "MT5 reports the order as filled, but no platform-owned entry deal was found yet."
                ],
                errors=[],
                message="Pending order is filled but execution evidence is incomplete.",
            )

        position_ticket = int(
            entry_deal.position_id
        )

        execution_price = self._decimal(
            entry_deal.price
        )

        if execution_price is None:
            return self._base_result(
                intent=intent,
                status="reconciliation_required",
                order_state=order_state,
                checks=checks,
                warnings=[],
                errors=[
                    "Filled MT5 entry deal has no valid execution price."
                ],
                message="The filled order cannot be reconciled safely.",
            )

        intent.pending_order_status = "filled"
        intent.execution_status = (
            "execution_reconciliation_required"
        )
        intent.execution_price = execution_price
        intent.deal_ticket = int(
            entry_deal.ticket
        )
        intent.filled_position_ticket = position_ticket
        intent.execution_time = self._timestamp(
            getattr(
                entry_deal,
                "time",
                None,
            )
        )
        intent.error_message = None
        intent.updated_at = self._now()

        db.commit()
        db.refresh(intent)

        checks.append(
            "Filled entry deal identified from the exact MT5 order ticket."
        )
        checks.append(
            "Actual MT5 position ticket identified from the entry deal."
        )

        reconciliation = (
            position_reconciliation_service.reconcile(
                db=db,
                user_id=int(user_id),
                intent_id=int(intent.id),
                position_ticket=position_ticket,
            )
        )

        checks.extend(
            reconciliation.checks
        )
        warnings.extend(
            reconciliation.warnings
        )
        errors.extend(
            reconciliation.errors
        )

        if reconciliation.reconciled:
            intent = (
                db.query(TradeIntent)
                .filter(
                    TradeIntent.id == int(intent.id),
                    TradeIntent.user_id == int(user_id),
                )
                .first()
            )

            if intent is not None:
                intent.execution_status = "executed"
                intent.pending_order_status = "filled"
                intent.execution_price = execution_price
                intent.deal_ticket = int(
                    entry_deal.ticket
                )
                intent.filled_position_ticket = position_ticket
                intent.execution_time = (
                    intent.execution_time
                    or self._timestamp(
                        getattr(
                            entry_deal,
                            "time",
                            None,
                        )
                    )
                )
                intent.error_message = None
                intent.updated_at = self._now()

                db.commit()

            return self._base_result(
                intent=intent,
                status="executed",
                order_state=order_state,
                checks=checks,
                warnings=warnings,
                errors=[],
                message="Pending order filled and live MT5 position reconciled successfully.",
                deal_ticket=int(entry_deal.ticket),
                position_ticket=position_ticket,
                execution_price=execution_price,
            )

        return self._base_result(
            intent=intent,
            status="filled_reconciliation_required",
            order_state=order_state,
            checks=checks,
            warnings=warnings,
            errors=errors,
            message="Pending order filled, but the resulting live MT5 position still requires reconciliation.",
            deal_ticket=int(entry_deal.ticket),
            position_ticket=position_ticket,
            execution_price=execution_price,
        )

    def reconcile_all_pending(
        self,
    ) -> list[PendingOrderReconciliationResult]:
        db = SessionLocal()

        try:
            intents = (
                db.query(TradeIntent)
                .filter(
                    TradeIntent.execution_mode == "pending",
                    TradeIntent.pending_order_status.in_(
                        ["placed", "partial"]
                    ),
                    TradeIntent.execution_status.in_(
                        [
                            "pending_order_placed",
                            "execution_reconciliation_required",
                        ]
                    ),
                    TradeIntent.order_ticket.isnot(None),
                )
                .all()
            )

            results: list[
                PendingOrderReconciliationResult
            ] = []

            for intent in intents:
                try:
                    results.append(
                        self.reconcile_intent(
                            db,
                            intent_id=int(intent.id),
                            user_id=int(intent.user_id),
                        )
                    )
                except Exception as exc:
                    db.rollback()

                    results.append(
                        self._base_result(
                            intent=intent,
                            status="reconciliation_required",
                            order_state=None,
                            checks=[],
                            warnings=[],
                            errors=[
                                f"Pending-order reconciliation failed: {exc}"
                            ],
                            message="Pending-order reconciliation encountered an unexpected error.",
                        )
                    )

            return results

        finally:
            db.close()


pending_order_reconciliation_service = (
    PendingOrderReconciliationService()
)
