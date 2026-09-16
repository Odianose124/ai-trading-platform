from __future__ import annotations

from dataclasses import dataclass

import MetaTrader5 as mt5
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.execution.position_manager import PositionManager
from app.models.managed_position import ManagedPosition
from app.models.management_profile import ManagementProfile
from app.models.mt5_trading_account import MT5TradingAccount
from app.models.trade_intent import TradeIntent
from app.mt5.connection import MT5ConnectionError, mt5_connection


class PositionReconciliationError(Exception):
    """Raised when an MT5 position cannot be safely reconciled."""


@dataclass
class PositionReconciliationResult:
    reconciled: bool
    status: str
    user_id: int | None
    mt5_account_id: int | None
    intent_id: int | None
    position_ticket: int | None
    broker_symbol: str | None
    direction: str | None
    volume: Decimal | None
    entry_price: Decimal | None
    current_price: Decimal | None
    stop_loss: Decimal | None
    take_profit: Decimal | None
    order_ticket: int | None
    deal_ticket: int | None
    managed_position_id: int | None
    checks: list[str]
    warnings: list[str]
    errors: list[str]
    message: str

    def serialize(self) -> dict[str, Any]:
        return {
            "reconciled": self.reconciled,
            "status": self.status,
            "user_id": self.user_id,
            "mt5_account_id": self.mt5_account_id,
            "intent_id": self.intent_id,
            "position_ticket": self.position_ticket,
            "broker_symbol": self.broker_symbol,
            "direction": self.direction,
            "volume": (
                float(self.volume)
                if self.volume is not None
                else None
            ),
            "entry_price": (
                float(self.entry_price)
                if self.entry_price is not None
                else None
            ),
            "current_price": (
                float(self.current_price)
                if self.current_price is not None
                else None
            ),
            "stop_loss": (
                float(self.stop_loss)
                if self.stop_loss is not None
                else None
            ),
            "take_profit": (
                float(self.take_profit)
                if self.take_profit is not None
                else None
            ),
            "order_ticket": self.order_ticket,
            "deal_ticket": self.deal_ticket,
            "managed_position_id": self.managed_position_id,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "message": self.message,
        }


class PositionReconciliationService:
    """
    Reconciles a confirmed MT5 execution with the actual live MT5 position.

    This service is deliberately conservative.

    It does NOT:
        - execute trades
        - call mt5.order_send()
        - create fake positions
        - assume that order_send() means a position exists
        - widen risk
        - modify broker positions
        - invent management rules

    Its responsibility is:

        execution result
            -> actual MT5 position
            -> validation
            -> ManagedPosition
            -> immutable ManagementProfile snapshot

    A position is only considered reconciled after the actual MT5
    position has been read and all critical execution attributes
    have been verified.
    """

    VOLUME_TOLERANCE = Decimal("0.00000001")
    DEFAULT_PRICE_TOLERANCE = Decimal("0.00000001")

    def __init__(
        self,
        position_manager: PositionManager | None = None,
    ) -> None:
        self.position_manager = (
            position_manager
            if position_manager is not None
            else PositionManager()
        )

    # ==============================================================
    # Basic helpers
    # ==============================================================

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value is None:
            return None

        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _normalize_direction(direction: Any) -> str:
        normalized = str(direction).strip().lower()

        if normalized in {"buy", "long"}:
            return "buy"

        if normalized in {"sell", "short"}:
            return "sell"

        return normalized

    @classmethod
    def _decimal_equal(
        cls,
        left: Any,
        right: Any,
        tolerance: Decimal,
    ) -> bool:
        left_decimal = cls._decimal(left)
        right_decimal = cls._decimal(right)

        if left_decimal is None or right_decimal is None:
            return False

        return abs(left_decimal - right_decimal) <= tolerance

    @classmethod
    def _price_tolerance(
        cls,
        broker_symbol: str | None,
    ) -> Decimal:
        """
        Determine a safe comparison tolerance from the actual MT5 symbol
        precision.

        MT5 may normalize submitted prices to the broker's configured
        number of digits. Reconciliation must therefore compare values
        at broker precision rather than requiring a mathematically exact
        decimal match.

        The fallback remains deliberately small if symbol metadata cannot
        be read.
        """

        symbol = (
            str(broker_symbol or "").strip()
        )

        if not symbol:
            return cls.DEFAULT_PRICE_TOLERANCE

        try:
            info = mt5.symbol_info(symbol)
        except Exception:
            info = None

        if info is None:
            return cls.DEFAULT_PRICE_TOLERANCE

        digits = getattr(info, "digits", None)

        try:
            digits = int(digits)
        except (TypeError, ValueError):
            return cls.DEFAULT_PRICE_TOLERANCE

        if digits < 0:
            return cls.DEFAULT_PRICE_TOLERANCE

        tolerance = Decimal("1").scaleb(-digits)

        if tolerance <= Decimal("0"):
            return cls.DEFAULT_PRICE_TOLERANCE

        return tolerance

    # ==============================================================
    # Result helpers
    # ==============================================================

    def _failure(
        self,
        *,
        user_id: int | None,
        mt5_account_id: int | None,
        intent_id: int | None,
        position_ticket: int | None,
        broker_symbol: str | None,
        direction: str | None,
        checks: list[str],
        warnings: list[str],
        errors: list[str],
        message: str,
    ) -> PositionReconciliationResult:
        return PositionReconciliationResult(
            reconciled=False,
            status="reconciliation_required",
            user_id=user_id,
            mt5_account_id=mt5_account_id,
            intent_id=intent_id,
            position_ticket=position_ticket,
            broker_symbol=broker_symbol,
            direction=direction,
            volume=None,
            entry_price=None,
            current_price=None,
            stop_loss=None,
            take_profit=None,
            order_ticket=None,
            deal_ticket=None,
            managed_position_id=None,
            checks=checks,
            warnings=warnings,
            errors=errors,
            message=message,
        )

    # ==============================================================
    # MT5 ownership
    # ==============================================================

    def _verify_mt5_connection(
        self,
        mt5_account: MT5TradingAccount,
    ) -> list[str]:
        checks: list[str] = []

        try:
            mt5_connection.ensure_connected()
        except MT5ConnectionError as exc:
            raise PositionReconciliationError(
                f"MT5 connection unavailable: {exc}"
            ) from exc

        try:
            mt5_connection.verify_account(
                expected_login=int(mt5_account.mt5_login),
                expected_server=str(mt5_account.server),
            )
        except Exception as exc:
            raise PositionReconciliationError(
                f"MT5 account ownership verification failed: {exc}"
            ) from exc

        checks.append("MT5 connection verified.")
        checks.append(
            "MT5 account login and server match the owned trading account."
        )

        return checks

    # ==============================================================
    # Position lookup
    # ==============================================================

    def _find_position(
        self,
        position_ticket: int,
    ) -> dict[str, Any] | None:
        return self.position_manager.get_position(position_ticket)

    def _find_position_from_intent(
        self,
        intent: TradeIntent,
    ) -> dict[str, Any] | None:
        """
        Resolve the actual MT5 position from broker execution evidence.

        The execution order/deal is NOT treated as a position ticket.

        Resolution is based on MT5 history:

            order ticket
                -> order/deal history
                -> position_id
                -> live MT5 position

        A symbol-only fallback is deliberately forbidden because another
        platform-owned position can already exist on the same symbol.
        """

        order_ticket = (
            int(intent.order_ticket)
            if intent.order_ticket is not None
            else None
        )

        deal_ticket = (
            int(intent.deal_ticket)
            if intent.deal_ticket is not None
            else None
        )

        candidate_position_ids: set[int] = set()

        # ----------------------------------------------------------
        # 1. Resolve through the execution order.
        # ----------------------------------------------------------

        if order_ticket is not None:
            try:
                orders = mt5.history_orders_get(
                    ticket=order_ticket
                )
            except Exception:
                orders = None

            if orders:
                for order in orders:
                    position_id = getattr(
                        order,
                        "position_id",
                        None,
                    )

                    if position_id:
                        candidate_position_ids.add(
                            int(position_id)
                        )

            try:
                deals = mt5.history_deals_get(
                    ticket=order_ticket
                )
            except Exception:
                deals = None

            if deals:
                for deal in deals:
                    position_id = getattr(
                        deal,
                        "position_id",
                        None,
                    )

                    if position_id:
                        candidate_position_ids.add(
                            int(position_id)
                        )

        # ----------------------------------------------------------
        # 2. If only a deal ticket is available, locate that deal
        #    in a narrow execution-time history window.
        # ----------------------------------------------------------

        if deal_ticket is not None and not candidate_position_ids:
            execution_time = (
                intent.execution_time
                or intent.confirmation_time
                or self._now()
            )

            try:
                timestamp = int(
                    execution_time.timestamp()
                )

                date_from = datetime.fromtimestamp(
                    max(timestamp - 300, 0),
                    tz=timezone.utc,
                )

                date_to = datetime.fromtimestamp(
                    timestamp + 300,
                    tz=timezone.utc,
                )

                deals = mt5.history_deals_get(
                    date_from,
                    date_to,
                )
            except Exception:
                deals = None

            if deals:
                for deal in deals:
                    if int(
                        getattr(deal, "ticket", 0)
                    ) != deal_ticket:
                        continue

                    position_id = getattr(
                        deal,
                        "position_id",
                        None,
                    )

                    if position_id:
                        candidate_position_ids.add(
                            int(position_id)
                        )

        # ----------------------------------------------------------
        # 3. Exactly one position identity must be proven.
        # ----------------------------------------------------------

        if len(candidate_position_ids) != 1:
            return None

        position_ticket = next(
            iter(candidate_position_ids)
        )

        position = self.position_manager.get_position(
            position_ticket
        )

        if position is None:
            return None

        return position


    # ==============================================================
    # Validation
    # ==============================================================

    def _validate_position_against_intent(
        self,
        intent: TradeIntent,
        position: dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        checks: list[str] = []
        errors: list[str] = []

        expected_symbol = (
            intent.broker_symbol
            or intent.symbol
        )

        actual_symbol = str(
            position.get("symbol") or ""
        ).strip()

        price_tolerance = self._price_tolerance(
            actual_symbol or expected_symbol
        )

        if actual_symbol.upper() != expected_symbol.upper():
            errors.append(
                "Reconciled position symbol does not match the trade intent."
            )
        else:
            checks.append("Broker symbol matches trade intent.")

        expected_direction = self._normalize_direction(
            intent.direction
        )

        actual_direction = self._normalize_direction(
            position.get("type")
        )

        if actual_direction != expected_direction:
            errors.append(
                "Reconciled position direction does not match the trade intent."
            )
        else:
            checks.append("Position direction matches trade intent.")

        expected_volume = self._decimal(intent.volume)
        actual_volume = self._decimal(position.get("volume"))

        if not self._decimal_equal(
            expected_volume,
            actual_volume,
            self.VOLUME_TOLERANCE,
        ):
            errors.append(
                "Reconciled position volume does not match the executed volume."
            )
        else:
            checks.append("Position volume matches executed volume.")

        expected_entry = self._decimal(
            intent.execution_price
        )

        actual_entry = self._decimal(
            position.get("entry_price")
        )

        if expected_entry is not None:
            if not self._decimal_equal(
                expected_entry,
                actual_entry,
                price_tolerance,
            ):
                errors.append(
                    "Reconciled position entry price does not match "
                    "the recorded execution price."
                )
            else:
                checks.append(
                    "Position entry price matches recorded execution price."
                )
        else:
            errors.append(
                "Trade intent has no recorded execution price."
            )

        expected_sl = self._decimal(
            intent.stop_loss
        )

        actual_sl = self._decimal(
            position.get("stop_loss")
        )

        if expected_sl is not None:
            if actual_sl is None:
                errors.append(
                    "Reconciled position has no stop loss."
                )
            elif not self._decimal_equal(
                expected_sl,
                actual_sl,
                price_tolerance,
            ):
                errors.append(
                    "Reconciled position stop loss does not match "
                    "the intended protective stop."
                )
            else:
                checks.append(
                    "Position stop loss matches trade intent."
                )

        expected_tp = self._decimal(
            intent.take_profit
        )

        actual_tp = self._decimal(
            position.get("take_profit")
        )

        if expected_tp is not None:
            if actual_tp is None:
                errors.append(
                    "Reconciled position has no take profit."
                )
            elif not self._decimal_equal(
                expected_tp,
                actual_tp,
                price_tolerance,
            ):
                errors.append(
                    "Reconciled position take profit does not match "
                    "the intended take profit."
                )
            else:
                checks.append(
                    "Position take profit matches trade intent."
                )

        return checks, errors

    # ==============================================================
    # ManagedPosition persistence
    # ==============================================================

    def _get_existing_managed_position(
        self,
        db: Session,
        position_ticket: int,
    ) -> ManagedPosition | None:
        return (
            db.query(ManagedPosition)
            .filter(
                ManagedPosition.position_ticket == position_ticket
            )
            .first()
        )

    def _create_managed_position(
        self,
        db: Session,
        *,
        intent: TradeIntent,
        mt5_account: MT5TradingAccount,
        position: dict[str, Any],
    ) -> ManagedPosition:
        entry_price = self._decimal(
            position.get("entry_price")
        )

        stop_loss = self._decimal(
            position.get("stop_loss")
        )

        if entry_price is None:
            raise PositionReconciliationError(
                "Actual MT5 position has no valid entry price."
            )

        if stop_loss is None:
            raise PositionReconciliationError(
                "Actual MT5 position has no valid stop loss."
            )

        initial_risk_distance = abs(
            entry_price - stop_loss
        )

        if initial_risk_distance <= Decimal("0"):
            raise PositionReconciliationError(
                "Actual MT5 position has an invalid initial risk distance."
            )

        managed_position = ManagedPosition(
            user_id=int(intent.user_id),
            mt5_account_id=int(mt5_account.id),
            trade_intent_id=int(intent.id),
            broker_symbol=str(
                position.get("symbol")
                or intent.broker_symbol
                or intent.symbol
            ),
            position_ticket=int(
                position["ticket"]
            ),
            order_ticket=(
                int(intent.order_ticket)
                if intent.order_ticket is not None
                else None
            ),
            deal_ticket=(
                int(intent.deal_ticket)
                if intent.deal_ticket is not None
                else None
            ),
            direction=self._normalize_direction(
                position.get("type")
            ),
            volume=self._decimal(
                position.get("volume")
            ),
            entry_price=entry_price,
            current_price=self._decimal(
                position.get("current_price")
            ),
            stop_loss=stop_loss,
            take_profit=self._decimal(
                position.get("take_profit")
            ),
            initial_stop_loss=stop_loss,
            initial_risk_distance=initial_risk_distance,
            status="open",
            profit_loss=(
                self._decimal(
                    position.get("profit")
                )
                or Decimal("0")
            ),
            opened_at=self._timestamp_to_datetime(
                position.get("time")
            ),
            last_reconciled_at=self._now(),
            created_at=self._now(),
            updated_at=self._now(),
        )

        db.add(managed_position)
        db.flush()

        return managed_position

    def _update_managed_position(
        self,
        managed_position: ManagedPosition,
        *,
        position: dict[str, Any],
    ) -> ManagedPosition:
        actual_volume = self._decimal(
            position.get("volume")
        )

        actual_entry = self._decimal(
            position.get("entry_price")
        )

        actual_current = self._decimal(
            position.get("current_price")
        )

        actual_sl = self._decimal(
            position.get("stop_loss")
        )

        actual_tp = self._decimal(
            position.get("take_profit")
        )

        actual_profit = (
            self._decimal(
                position.get("profit")
            )
            or Decimal("0")
        )

        if actual_volume is not None:
            managed_position.volume = actual_volume

        if actual_entry is not None:
            managed_position.entry_price = actual_entry

        managed_position.current_price = actual_current
        managed_position.stop_loss = actual_sl
        managed_position.take_profit = actual_tp
        managed_position.profit_loss = actual_profit
        managed_position.status = "open"
        managed_position.last_reconciled_at = self._now()
        managed_position.updated_at = self._now()

        return managed_position

    @staticmethod
    def _timestamp_to_datetime(
        timestamp: Any,
    ) -> datetime:
        if timestamp is None:
            return datetime.now(timezone.utc)

        try:
            return datetime.fromtimestamp(
                int(timestamp),
                tz=timezone.utc,
            )
        except (TypeError, ValueError, OSError):
            return datetime.now(timezone.utc)

    # ==============================================================
    # Management profile
    # ==============================================================

    def _create_management_profile(
        self,
        db: Session,
        managed_position: ManagedPosition,
    ) -> ManagementProfile:
        """
        Create the immutable management snapshot.

        At this infrastructure stage we deliberately use safe,
        inactive numeric thresholds rather than inventing trading
        strategy values.

        AI management is therefore disabled until the explicit
        management-profile configuration stage supplies real rules.

        The boolean defaults on the database model are not enough
        to create an executable strategy because all trigger values
        are nullable.
        """

        profile = ManagementProfile(
            managed_position_id=managed_position.id,
            profile_name="Pending Configuration",
            ai_management_enabled=False,

            break_even_enabled=False,
            break_even_trigger_r=None,
            break_even_offset=None,

            partial_profit_enabled=False,
            partial_1_trigger_r=None,
            partial_1_percent=None,
            partial_2_trigger_r=None,
            partial_2_percent=None,

            profit_protection_enabled=False,
            profit_protection_trigger_r=None,
            locked_profit_r=None,

            trailing_enabled=False,
            trailing_method=None,
            trailing_activation_r=None,
            trailing_distance_r=None,

            invalidation_protection_enabled=False,
            close_on_invalidation=False,

            max_management_duration_minutes=None,

            snapshot_version=1,
            created_at=self._now(),
        )

        db.add(profile)
        db.flush()

        return profile

    def _ensure_management_profile(
        self,
        db: Session,
        managed_position: ManagedPosition,
    ) -> ManagementProfile:
        existing = (
            db.query(ManagementProfile)
            .filter(
                ManagementProfile.managed_position_id
                == managed_position.id
            )
            .first()
        )

        if existing is not None:
            return existing

        return self._create_management_profile(
            db,
            managed_position,
        )

    # ==============================================================
    # Main reconciliation
    # ==============================================================

    def reconcile(
        self,
        db: Session,
        *,
        user_id: int,
        intent_id: int,
        position_ticket: int | None = None,
    ) -> PositionReconciliationResult:
        """
        Reconcile a confirmed execution with the actual MT5 position.

        This is the primary entry point.

        It is safe to call repeatedly for an already reconciled position.
        Reconciliation updates broker state but does not create duplicate
        ManagedPosition or ManagementProfile records.
        """

        checks: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []

        # ----------------------------------------------------------
        # 1. Load owned intent
        # ----------------------------------------------------------

        intent = (
            db.query(TradeIntent)
            .filter(
                TradeIntent.id == intent_id,
                TradeIntent.user_id == user_id,
            )
            .first()
        )

        if intent is None:
            return self._failure(
                user_id=user_id,
                mt5_account_id=None,
                intent_id=intent_id,
                position_ticket=position_ticket,
                broker_symbol=None,
                direction=None,
                checks=checks,
                warnings=warnings,
                errors=["Trade intent was not found."],
                message=(
                    "The trade intent could not be found "
                    "for the authenticated user."
                ),
            )

        checks.append(
            "Trade intent ownership verified."
        )

        # ----------------------------------------------------------
        # 2. Intent must represent an execution attempt
        # ----------------------------------------------------------

        if intent.execution_status not in {
            "executed",
            "executing",
            "execution_unknown",
            "execution_reconciliation_required",
        }:
            errors.append(
                "Trade intent is not in a state that can be reconciled."
            )

            return self._failure(
                user_id=user_id,
                mt5_account_id=None,
                intent_id=intent.id,
                position_ticket=position_ticket,
                broker_symbol=intent.broker_symbol or intent.symbol,
                direction=self._normalize_direction(
                    intent.direction
                ),
                checks=checks,
                warnings=warnings,
                errors=errors,
                message=(
                    "Position reconciliation requires an execution "
                    "attempt that may have reached MT5."
                ),
            )

        # ----------------------------------------------------------
        # 3. Resolve owned MT5 trading account
        # ----------------------------------------------------------

        mt5_account = (
            db.query(MT5TradingAccount)
            .filter(
                MT5TradingAccount.user_id == user_id,
                MT5TradingAccount.is_active.is_(True),
            )
            .first()
        )

        if mt5_account is None:
            return self._failure(
                user_id=user_id,
                mt5_account_id=None,
                intent_id=intent.id,
                position_ticket=position_ticket,
                broker_symbol=intent.broker_symbol or intent.symbol,
                direction=self._normalize_direction(
                    intent.direction
                ),
                checks=checks,
                warnings=warnings,
                errors=[
                    "No active MT5 trading account is assigned to the user."
                ],
                message=(
                    "The MT5 trading account could not be resolved."
                ),
            )

        checks.extend(
            self._verify_mt5_connection(
                mt5_account
            )
        )

        # ----------------------------------------------------------
        # 4. Find actual broker position
        # ----------------------------------------------------------

        actual_position = None

        if position_ticket is not None:
            try:
                actual_position = self._find_position(
                    int(position_ticket)
                )
            except (TypeError, ValueError):
                actual_position = None

        if actual_position is None:
            actual_position = self._find_position_from_intent(
                intent
            )

        if actual_position is None:
            errors.append(
                "The resulting MT5 position could not be proven."
            )

            warnings.append(
                "Execution must remain reconciliation-required; "
                "another execution attempt must not be started automatically."
            )

            return self._failure(
                user_id=user_id,
                mt5_account_id=mt5_account.id,
                intent_id=intent.id,
                position_ticket=position_ticket,
                broker_symbol=intent.broker_symbol or intent.symbol,
                direction=self._normalize_direction(
                    intent.direction
                ),
                checks=checks,
                warnings=warnings,
                errors=errors,
                message=(
                    "MT5 accepted or may have accepted the execution, "
                    "but the resulting live position could not be proven."
                ),
            )

        checks.append(
            "Actual live MT5 position was found."
        )

        actual_ticket = int(
            actual_position["ticket"]
        )

        # ----------------------------------------------------------
        # 5. Validate actual position against intent
        # ----------------------------------------------------------

        validation_checks, validation_errors = (
            self._validate_position_against_intent(
                intent,
                actual_position,
            )
        )

        checks.extend(validation_checks)
        errors.extend(validation_errors)

        if errors:
            warnings.append(
                "The broker position exists but does not fully match "
                "the server-side execution intent."
            )

            return self._failure(
                user_id=user_id,
                mt5_account_id=mt5_account.id,
                intent_id=intent.id,
                position_ticket=actual_ticket,
                broker_symbol=str(
                    actual_position.get("symbol")
                    or intent.broker_symbol
                    or intent.symbol
                ),
                direction=self._normalize_direction(
                    actual_position.get("type")
                ),
                checks=checks,
                warnings=warnings,
                errors=errors,
                message=(
                    "The live MT5 position was found, but reconciliation "
                    "failed validation. Manual investigation is required."
                ),
            )

        # ----------------------------------------------------------
        # 6. Persist managed position
        # ----------------------------------------------------------

        managed_position = self._get_existing_managed_position(
            db,
            actual_ticket,
        )

        if managed_position is None:
            managed_position = self._create_managed_position(
                db,
                intent=intent,
                mt5_account=mt5_account,
                position=actual_position,
            )

            checks.append(
                "ManagedPosition created from the actual MT5 position."
            )

        else:
            if managed_position.user_id != user_id:
                db.rollback()

                return self._failure(
                    user_id=user_id,
                    mt5_account_id=mt5_account.id,
                    intent_id=intent.id,
                    position_ticket=actual_ticket,
                    broker_symbol=actual_position.get("symbol"),
                    direction=actual_position.get("type"),
                    checks=checks,
                    warnings=warnings,
                    errors=[
                        "Existing managed position belongs to another user."
                    ],
                    message=(
                        "Position ownership conflict detected. "
                        "No changes were persisted."
                    ),
                )

            if managed_position.mt5_account_id != mt5_account.id:
                db.rollback()

                return self._failure(
                    user_id=user_id,
                    mt5_account_id=mt5_account.id,
                    intent_id=intent.id,
                    position_ticket=actual_ticket,
                    broker_symbol=actual_position.get("symbol"),
                    direction=actual_position.get("type"),
                    checks=checks,
                    warnings=warnings,
                    errors=[
                        "Existing managed position belongs to another "
                        "MT5 trading account."
                    ],
                    message=(
                        "MT5 account ownership conflict detected. "
                        "No changes were persisted."
                    ),
                )

            self._update_managed_position(
                managed_position,
                position=actual_position,
            )

            checks.append(
                "Existing ManagedPosition reconciled with current MT5 state."
            )

        # ----------------------------------------------------------
        # 7. Create immutable management snapshot
        # ----------------------------------------------------------

        management_profile = self._ensure_management_profile(
            db,
            managed_position,
        )

        if management_profile is not None:
            checks.append(
                "ManagementProfile snapshot exists for the managed position."
            )

        # ----------------------------------------------------------
        # 8. Persist reconciliation only.
        #
        # TradeIntent execution status is owned by the confirmation
        # service. This service proves and persists the actual broker
        # position but does not declare the trade executed.
        # ----------------------------------------------------------

        db.commit()

        db.refresh(managed_position)

        checks.append(
            "Live MT5 position successfully reconciled and persisted."
        )

        return PositionReconciliationResult(
            reconciled=True,
            status="reconciled",
            user_id=user_id,
            mt5_account_id=mt5_account.id,
            intent_id=intent.id,
            position_ticket=actual_ticket,
            broker_symbol=str(
                actual_position.get("symbol")
                or intent.broker_symbol
                or intent.symbol
            ),
            direction=self._normalize_direction(
                actual_position.get("type")
            ),
            volume=self._decimal(
                actual_position.get("volume")
            ),
            entry_price=self._decimal(
                actual_position.get("entry_price")
            ),
            current_price=self._decimal(
                actual_position.get("current_price")
            ),
            stop_loss=self._decimal(
                actual_position.get("stop_loss")
            ),
            take_profit=self._decimal(
                actual_position.get("take_profit")
            ),
            order_ticket=(
                int(intent.order_ticket)
                if intent.order_ticket is not None
                else None
            ),
            deal_ticket=(
                int(intent.deal_ticket)
                if intent.deal_ticket is not None
                else None
            ),
            managed_position_id=managed_position.id,
            checks=checks,
            warnings=warnings,
            errors=[],
            message=(
                "MT5 execution was reconciled against the actual live "
                "position and persisted successfully."
            ),
        )


position_reconciliation_service = PositionReconciliationService()