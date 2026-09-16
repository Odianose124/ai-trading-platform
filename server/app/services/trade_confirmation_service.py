from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import and_, update
from sqlalchemy.orm import Session

from app.models.trade_intent import TradeIntent
from app.models.user_settings import UserSettings
from app.models.mt5_trading_account import MT5TradingAccount
from app.execution.position_manager import PositionManager
from app.mt5.connection import (
    MT5AccountMismatchError,
    MT5ConnectionError,
    mt5_connection,
)
from app.services.broker_validation_service import (
    broker_validation_service,
)
from app.services.mt5_execution_service import (
    mt5_execution_service,
)
from app.services.position_reconciliation_service import (
    position_reconciliation_service,
)


class TradeConfirmationError(Exception):
    """Raised when trade confirmation cannot be completed."""


@dataclass
class TradeConfirmationResult:
    approved: bool
    status: str
    intent_id: int | None
    user_id: int | None
    symbol: str | None
    broker_symbol: str | None
    direction: str | None
    volume: Decimal | None
    requested_entry_price: Decimal | None
    execution_price: Decimal | None
    execution_mode: str | None
    order_type: str | None
    pending_order_status: str | None
    pending_order_placed_at: datetime | None
    filled_position_ticket: int | None
    stop_loss: Decimal | None
    take_profit: Decimal | None
    signal_price_deviation: Decimal | None
    signal_price_deviation_percent: Decimal | None
    order_ticket: int | None
    deal_ticket: int | None
    retcode: int | None
    retcode_description: str | None
    margin_required: Decimal | None
    free_margin: Decimal | None
    risk_amount: Decimal | None
    risk_percent: Decimal | None
    confirmation_time: datetime | None
    execution_time: datetime | None
    checks: list[str]
    warnings: list[str]
    errors: list[str]
    execution_sent: bool
    message: str

    def serialize(self) -> dict:
        return {
            "approved": self.approved,
            "status": self.status,
            "intent_id": self.intent_id,
            "user_id": self.user_id,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "direction": self.direction,
            "volume": (
                float(self.volume)
                if self.volume is not None
                else None
            ),
            "requested_entry_price": (
                float(self.requested_entry_price)
                if self.requested_entry_price is not None
                else None
            ),
            "execution_price": (
                float(self.execution_price)
                if self.execution_price is not None
                else None
            ),
            "execution_mode": self.execution_mode,
            "order_type": self.order_type,
            "pending_order_status": self.pending_order_status,
            "pending_order_placed_at": (
                self.pending_order_placed_at.isoformat()
                if self.pending_order_placed_at is not None
                else None
            ),
            "filled_position_ticket": self.filled_position_ticket,
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
            "signal_price_deviation": (
                float(self.signal_price_deviation)
                if self.signal_price_deviation is not None
                else None
            ),
            "signal_price_deviation_percent": (
                float(self.signal_price_deviation_percent)
                if self.signal_price_deviation_percent is not None
                else None
            ),
            "order_ticket": self.order_ticket,
            "deal_ticket": self.deal_ticket,
            "retcode": self.retcode,
            "retcode_description": self.retcode_description,
            "margin_required": (
                float(self.margin_required)
                if self.margin_required is not None
                else None
            ),
            "free_margin": (
                float(self.free_margin)
                if self.free_margin is not None
                else None
            ),
            "risk_amount": (
                float(self.risk_amount)
                if self.risk_amount is not None
                else None
            ),
            "risk_percent": (
                float(self.risk_percent)
                if self.risk_percent is not None
                else None
            ),
            "confirmation_time": (
                self.confirmation_time.isoformat()
                if self.confirmation_time is not None
                else None
            ),
            "execution_time": (
                self.execution_time.isoformat()
                if self.execution_time is not None
                else None
            ),
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "execution_sent": self.execution_sent,
            "message": self.message,
        }


class TradeConfirmationService:
    """
    Handles final trade confirmation and MT5 execution.

    Security rules:

    1. The client supplies only the trade intent ID.
    2. Trading parameters are loaded from the server-side intent.
    3. User ownership is verified.
    4. Pending status is verified.
    5. Expiration is verified.
    6. The intent is atomically claimed before execution.
    7. A second confirmation cannot claim the same intent.
    8. Fresh broker validation is performed after claiming.
    9. Server-side execution information is refreshed.
    10. The MT5 execution service performs its own final checks.
    11. mt5.order_send() is reached only after explicit confirmation.
    """

    MAX_SIGNAL_DEVIATION_PERCENT = Decimal("0.25")

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _normalize_direction(self, direction: str) -> str:
        normalized = str(direction).strip().lower()

        if normalized in {"long", "buy"}:
            return "buy"

        if normalized in {"short", "sell"}:
            return "sell"

        raise TradeConfirmationError(
            "Trade intent contains an invalid direction."
        )

    def _load_owned_intent(
        self,
        db: Session,
        intent_id: int,
        user_id: int,
    ) -> TradeIntent | None:
        return (
            db.query(TradeIntent)
            .filter(
                TradeIntent.id == intent_id,
                TradeIntent.user_id == user_id,
            )
            .first()
        )

    def _build_result(
        self,
        intent: TradeIntent | None,
        *,
        approved: bool,
        status: str,
        checks: list[str] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        order_ticket: int | None = None,
        deal_ticket: int | None = None,
        retcode: int | None = None,
        retcode_description: str | None = None,
        margin_required: Decimal | None = None,
        free_margin: Decimal | None = None,
        risk_amount: Decimal | None = None,
        risk_percent: Decimal | None = None,
        signal_price_deviation: Decimal | None = None,
        signal_price_deviation_percent: Decimal | None = None,
        execution_sent: bool = False,
        message: str = "",
    ) -> TradeConfirmationResult:

        return TradeConfirmationResult(
            approved=approved,
            status=status,
            intent_id=intent.id if intent else None,
            user_id=intent.user_id if intent else None,
            symbol=intent.symbol if intent else None,
            broker_symbol=(
                intent.broker_symbol
                if intent
                else None
            ),
            direction=(
                self._normalize_direction(intent.direction)
                if intent
                else None
            ),
            volume=(
                intent.volume
                if intent
                else None
            ),
            requested_entry_price=(
                intent.signal_entry_price
                if intent
                else None
            ),
            execution_price=(
                intent.execution_price
                if intent
                else None
            ),
            execution_mode=(
                getattr(intent, "execution_mode", None)
                if intent
                else None
            ),
            order_type=(
                getattr(intent, "order_type", None)
                if intent
                else None
            ),
            pending_order_status=(
                getattr(intent, "pending_order_status", None)
                if intent
                else None
            ),
            pending_order_placed_at=(
                getattr(intent, "pending_order_placed_at", None)
                if intent
                else None
            ),
            filled_position_ticket=(
                getattr(intent, "filled_position_ticket", None)
                if intent
                else None
            ),
            stop_loss=(
                intent.stop_loss
                if intent
                else None
            ),
            take_profit=(
                intent.take_profit
                if intent
                else None
            ),
            signal_price_deviation=(
                signal_price_deviation
                if signal_price_deviation is not None
                else (
                    getattr(
                        intent,
                        "signal_price_deviation",
                        None,
                    )
                    if intent
                    else None
                )
            ),
            signal_price_deviation_percent=(
                signal_price_deviation_percent
                if signal_price_deviation_percent is not None
                else (
                    getattr(
                        intent,
                        "signal_price_deviation_percent",
                        None,
                    )
                    if intent
                    else None
                )
            ),
            order_ticket=order_ticket,
            deal_ticket=deal_ticket,
            retcode=retcode,
            retcode_description=retcode_description,
            margin_required=margin_required,
            free_margin=free_margin,
            risk_amount=risk_amount,
            risk_percent=(
                risk_percent
                if risk_percent is not None
                else (
                    intent.risk_percent
                    if intent
                    else None
                )
            ),
            confirmation_time=(
                intent.confirmation_time
                if intent
                else None
            ),
            execution_time=(
                intent.execution_time
                if intent
                else None
            ),
            checks=checks or [],
            warnings=warnings or [],
            errors=errors or [],
            execution_sent=execution_sent,
            message=message,
        )

    def _claim_intent(
        self,
        db: Session,
        intent_id: int,
        user_id: int,
    ) -> bool:
        """
        Atomically claim a pending trade intent.

        Only one request can successfully transition:

            pending + not_executed

        into:

            confirmed + executing
        """

        now = self._now()

        result = db.execute(
            update(TradeIntent)
            .where(
                and_(
                    TradeIntent.id == intent_id,
                    TradeIntent.user_id == user_id,
                    TradeIntent.confirmation_status == "pending",
                    TradeIntent.execution_status == "not_executed",
                )
            )
            .values(
                confirmation_status="confirmed",
                execution_status="executing",
                confirmation_time=now,
                updated_at=now,
            )
        )

        if result.rowcount != 1:
            db.rollback()
            return False

        db.commit()

        return True

    def _get_max_open_trades(
        self,
        db: Session,
        user_id: int,
    ) -> int:
        settings = (
            db.query(UserSettings)
            .filter(
                UserSettings.user_id == user_id
            )
            .first()
        )

        if settings is None:
            return 3

        return int(settings.max_open_trades)


    def _get_verified_mt5_account(
        self,
        db: Session,
        user_id: int,
    ) -> MT5TradingAccount:
        """
        Resolve and verify the MT5 account owned by the authenticated user.

        This check is intentionally performed inside the confirmation
        service so execution cannot depend on a previous API-layer check.
        """

        account = (
            db.query(MT5TradingAccount)
            .filter(
                MT5TradingAccount.user_id == user_id,
                MT5TradingAccount.is_active.is_(True),
            )
            .first()
        )

        if account is None:
            raise TradeConfirmationError(
                "No active MetaTrader 5 trading account is registered "
                "for this user."
            )

        try:
            mt5_connection.verify_account(
                expected_login=account.mt5_login,
                expected_server=account.server,
            )
        except MT5AccountMismatchError as exc:
            raise TradeConfirmationError(
                "The currently connected MetaTrader 5 account does not "
                "belong to the authenticated user."
            ) from exc
        except MT5ConnectionError as exc:
            raise TradeConfirmationError(
                "MetaTrader 5 ownership could not be verified because "
                "the trading terminal is unavailable."
            ) from exc

        return account

    def _get_verified_open_positions(
        self,
        db: Session,
        user_id: int,
    ) -> tuple[MT5TradingAccount, list[dict]]:
        """
        Verify MT5 ownership first, then read platform-owned positions.

        PositionManager is deliberately called only after the live MT5
        login/server has been verified against the authenticated user.
        """

        account = self._get_verified_mt5_account(
            db,
            user_id,
        )

        position_manager = PositionManager()

        try:
            open_positions = position_manager.get_positions()
        except MT5ConnectionError as exc:
            raise TradeConfirmationError(
                "Open MT5 positions could not be read after account "
                "ownership verification."
            ) from exc

        return account, open_positions

    def _check_max_open_trades(
        self,
        db: Session,
        user_id: int,
        open_positions: list[dict],
    ) -> tuple[bool, int, int]:
        max_open_trades = self._get_max_open_trades(
            db,
            user_id,
        )

        open_count = len(open_positions)

        return (
            open_count < max_open_trades,
            open_count,
            max_open_trades,
        )


    def _mark_rejected(
        self,
        db: Session,
        intent: TradeIntent,
        error_message: str,
    ) -> None:

        now = self._now()

        intent.confirmation_status = "rejected"
        intent.execution_status = "rejected"
        intent.error_message = error_message
        intent.updated_at = now

        db.commit()
        db.refresh(intent)

    def _mark_expired(
        self,
        db: Session,
        intent: TradeIntent,
        error_message: str,
    ) -> None:

        now = self._now()

        intent.confirmation_status = "expired"
        intent.execution_status = "blocked"
        intent.error_message = error_message
        intent.updated_at = now

        db.commit()
        db.refresh(intent)

    def _mark_execution_unknown(
        self,
        db: Session,
        intent: TradeIntent,
        error_message: str,
    ) -> None:
        """
        Used when execution processing fails unexpectedly.

        We deliberately do not mark the trade as rejected because
        an unexpected failure can occur after an execution attempt
        has already reached the broker.

        This state requires reconciliation before another
        execution attempt is allowed.
        """

        now = self._now()

        intent.confirmation_status = "confirmed"
        intent.execution_status = "execution_unknown"
        intent.error_message = error_message
        intent.updated_at = now

        db.commit()
        db.refresh(intent)

    def _mark_execution_result(
        self,
        db: Session,
        intent: TradeIntent,
        execution_result,
    ) -> None:

        now = self._now()

        execution_approved = bool(
            getattr(
                execution_result,
                "approved",
                False,
            )
        )

        execution_sent = bool(
            getattr(
                execution_result,
                "execution_sent",
                False,
            )
        )

        # ---------------------------------------------------------
        # Persist all final broker/execution information available.
        # ---------------------------------------------------------

        broker_symbol = getattr(
            execution_result,
            "broker_symbol",
            None,
        )

        if broker_symbol:
            intent.broker_symbol = broker_symbol

        execution_price = getattr(
            execution_result,
            "execution_price",
            None,
        )

        if execution_price is not None:
            intent.execution_price = execution_price

        margin_required = getattr(
            execution_result,
            "margin_required",
            None,
        )

        if margin_required is not None:
            intent.margin_required = margin_required

        free_margin = getattr(
            execution_result,
            "free_margin",
            None,
        )

        if free_margin is not None:
            intent.free_margin = free_margin

        signal_deviation_percent = getattr(
            execution_result,
            "signal_price_deviation_percent",
            None,
        )

        if signal_deviation_percent is not None:
            intent.signal_price_deviation_percent = (
                signal_deviation_percent
            )

        execution_mode = getattr(
            execution_result,
            "execution_mode",
            getattr(intent, "execution_mode", "market"),
        )

        order_type = getattr(
            execution_result,
            "order_type",
            getattr(intent, "order_type", "MARKET"),
        )

        pending_order_status = getattr(
            execution_result,
            "pending_order_status",
            getattr(intent, "pending_order_status", "not_applicable"),
        )

        intent.execution_mode = execution_mode
        intent.order_type = order_type
        intent.pending_order_status = pending_order_status

        # ---------------------------------------------------------
        # Successful pending-order placement
        # ---------------------------------------------------------

        if (
            execution_approved
            and execution_sent
            and execution_mode == "pending"
        ):
            intent.confirmation_status = "confirmed"
            intent.execution_status = "pending_order_placed"
            intent.pending_order_status = "placed"
            intent.pending_order_placed_at = now
            intent.execution_price = None
            intent.deal_ticket = None
            intent.filled_position_ticket = None

            intent.order_ticket = getattr(
                execution_result,
                "order_ticket",
                None,
            )

            intent.retcode = getattr(
                execution_result,
                "retcode",
                None,
            )

            intent.retcode_description = getattr(
                execution_result,
                "retcode_description",
                None,
            )

            intent.execution_time = None
            intent.error_message = None

        # ---------------------------------------------------------
        # Successful market execution
        # ---------------------------------------------------------

        elif execution_approved and execution_sent:

            intent.confirmation_status = "confirmed"
            intent.execution_status = "execution_reconciliation_required"

            intent.order_ticket = getattr(
                execution_result,
                "order_ticket",
                None,
            )

            intent.deal_ticket = getattr(
                execution_result,
                "deal_ticket",
                None,
            )

            intent.retcode = getattr(
                execution_result,
                "retcode",
                None,
            )

            intent.retcode_description = getattr(
                execution_result,
                "retcode_description",
                None,
            )

            intent.execution_time = now
            intent.error_message = None

        # ---------------------------------------------------------
        # Execution explicitly rejected by MT5/execution service
        # ---------------------------------------------------------

        else:

            intent.execution_status = "rejected"

            intent.order_ticket = getattr(
                execution_result,
                "order_ticket",
                None,
            )

            intent.deal_ticket = getattr(
                execution_result,
                "deal_ticket",
                None,
            )

            intent.retcode = getattr(
                execution_result,
                "retcode",
                None,
            )

            intent.retcode_description = getattr(
                execution_result,
                "retcode_description",
                None,
            )

            execution_errors = getattr(
                execution_result,
                "errors",
                [],
            )

            execution_message = getattr(
                execution_result,
                "message",
                "MT5 execution was rejected.",
            )

            intent.error_message = (
                "; ".join(execution_errors)
                if execution_errors
                else execution_message
            )

        intent.updated_at = now

        db.commit()
        db.refresh(intent)

    def confirm(
        self,
        db: Session,
        intent_id: int,
        user_id: int,
    ) -> TradeConfirmationResult:
        """
        Confirm and execute a server-side trade intent.

        The client supplies only intent_id.

        The service loads every trading parameter from the
        server-side intent and performs fresh validation before
        allowing the MT5 execution service to run.
        """

        if intent_id <= 0:
            raise TradeConfirmationError(
                "Intent ID must be greater than zero."
            )

        if user_id is None:
            raise TradeConfirmationError(
                "Authenticated user is required."
            )

        # =========================================================
        # 1. LOAD OWNED INTENT
        # =========================================================

        intent = self._load_owned_intent(
            db,
            intent_id,
            user_id,
        )

        if intent is None:
            raise TradeConfirmationError(
                "Trade intent not found."
            )

        checks: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []

        # =========================================================
        # 2. CONFIRMATION STATUS
        # =========================================================

        if intent.confirmation_status != "pending":

            return self._build_result(
                intent,
                approved=False,
                status="already_processed",
                errors=[
                    (
                        "Trade intent is no longer pending "
                        "confirmation."
                    )
                ],
                message=(
                    "Trade intent has already been processed "
                    "or is currently being processed."
                ),
            )

        # =========================================================
        # 3. EXECUTION STATUS
        # =========================================================

        if intent.execution_status != "not_executed":

            return self._build_result(
                intent,
                approved=False,
                status="already_processed",
                errors=[
                    (
                        "Trade intent execution is no longer "
                        "pending."
                    )
                ],
                message=(
                    "Trade intent cannot be confirmed again."
                ),
            )

        # =========================================================
        # 4. EXPIRATION
        # =========================================================

        now = self._now()

        if intent.expires_at is None:

            self._mark_expired(
                db,
                intent,
                "Trade intent has no expiration time.",
            )

            return self._build_result(
                intent,
                approved=False,
                status="expired",
                errors=[
                    "Trade intent has no expiration time."
                ],
                message=(
                    "Trade intent cannot be confirmed."
                ),
            )

        expires_at = intent.expires_at

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(
                tzinfo=timezone.utc
            )

        if now >= expires_at:

            self._mark_expired(
                db,
                intent,
                "Trade intent expired before confirmation.",
            )

            return self._build_result(
                intent,
                approved=False,
                status="expired",
                errors=[
                    (
                        "Trade intent expired before "
                        "confirmation."
                    )
                ],
                message=(
                    "Trade intent has expired and cannot "
                    "be executed."
                ),
            )

        checks.extend(
            [
                "Authenticated user ownership verified",
                "Trade intent is pending",
                "Trade intent has not been executed",
                "Trade intent expiration verified",
            ]
        )

        # =========================================================
        # 5. VERIFY MT5 OWNERSHIP + MAXIMUM OPEN TRADES
        # =========================================================

        try:
            (
                verified_mt5_account,
                verified_open_positions,
            ) = self._get_verified_open_positions(
                db,
                user_id,
            )

        except TradeConfirmationError as exc:
            error_message = str(exc)

            self._mark_rejected(
                db,
                intent,
                error_message,
            )

            return self._build_result(
                intent,
                approved=False,
                status="rejected",
                checks=checks,
                errors=[error_message],
                message=(
                    "Trade confirmation was rejected because "
                    "MetaTrader 5 account ownership could not be verified."
                ),
            )

        checks.append(
            (
                "MT5 account ownership verified: "
                f"{verified_mt5_account.mt5_login}/"
                f"{verified_mt5_account.server}"
            )
        )

        (
            open_trades_allowed,
            current_open_trades,
            max_open_trades,
        ) = self._check_max_open_trades(
            db,
            user_id,
            verified_open_positions,
        )

        if not open_trades_allowed:
            error_message = (
                "Maximum open trades reached. "
                f"You currently have {current_open_trades} "
                f"AI-managed open trade(s), and your configured "
                f"maximum is {max_open_trades}."
            )

            self._mark_rejected(
                db,
                intent,
                error_message,
            )

            return self._build_result(
                intent,
                approved=False,
                status="rejected",
                checks=checks,
                errors=[
                    error_message
                ],
                message=(
                    "Trade confirmation rejected because "
                    "the maximum number of open trades has "
                    "already been reached."
                ),
            )

        checks.append(
            (
                "Maximum open trades check passed: "
                f"{current_open_trades}/{max_open_trades}"
            )
        )

        # =========================================================
        # 6. ATOMIC CLAIM
        # =========================================================

        claimed = self._claim_intent(
            db,
            intent_id,
            user_id,
        )

        if not claimed:

            db.expire_all()

            refreshed_intent = self._load_owned_intent(
                db,
                intent_id,
                user_id,
            )

            return self._build_result(
                refreshed_intent,
                approved=False,
                status="already_processed",
                errors=[
                    (
                        "Trade intent was already claimed "
                        "by another confirmation request."
                    )
                ],
                message=(
                    "Trade intent cannot be confirmed again. "
                    "Only one confirmation request can claim "
                    "an intent."
                ),
            )

        # =========================================================
        # 6. RELOAD AFTER CLAIM
        # =========================================================

        intent = self._load_owned_intent(
            db,
            intent_id,
            user_id,
        )

        if intent is None:
            raise TradeConfirmationError(
                (
                    "Trade intent could not be reloaded "
                    "after confirmation claim."
                )
            )

        checks.append(
            "Trade intent atomically claimed for execution"
        )

        # =========================================================
        # 7. SERVER-SIDE DIRECTION
        # =========================================================

        try:

            direction = self._normalize_direction(
                intent.direction
            )

        except TradeConfirmationError as exc:

            self._mark_rejected(
                db,
                intent,
                str(exc),
            )

            return self._build_result(
                intent,
                approved=False,
                status="rejected",
                checks=checks,
                errors=[str(exc)],
                message=(
                    "Trade confirmation rejected because "
                    "the stored direction is invalid."
                ),
            )

        checks.append(
            "Server-side trade direction validated"
        )

        # =========================================================
        # 8. FINAL MT5 OWNERSHIP + OPEN-TRADE RE-CHECK
        # =========================================================

        try:
            (
                verified_mt5_account,
                verified_open_positions,
            ) = self._get_verified_open_positions(
                db,
                user_id,
            )

        except TradeConfirmationError as exc:
            error_message = str(exc)

            self._mark_rejected(
                db,
                intent,
                error_message,
            )

            return self._build_result(
                intent,
                approved=False,
                status="rejected",
                checks=checks,
                warnings=warnings,
                errors=[error_message],
                message=(
                    "Trade confirmation was blocked because the "
                    "MetaTrader 5 account could not be re-verified "
                    "immediately before broker validation."
                ),
            )

        checks.append(
            (
                "Final MT5 account ownership verification passed: "
                f"{verified_mt5_account.mt5_login}/"
                f"{verified_mt5_account.server}"
            )
        )

        (
            open_trades_allowed,
            current_open_trades,
            max_open_trades,
        ) = self._check_max_open_trades(
            db,
            user_id,
            verified_open_positions,
        )

        if not open_trades_allowed:
            error_message = (
                "Maximum open trades reached before execution. "
                f"You currently have {current_open_trades} "
                f"AI-managed open trade(s), and your configured "
                f"maximum is {max_open_trades}."
            )

            self._mark_rejected(
                db,
                intent,
                error_message,
            )

            return self._build_result(
                intent,
                approved=False,
                status="rejected",
                checks=checks,
                warnings=warnings,
                errors=[
                    error_message
                ],
                message=(
                    "Trade confirmation was blocked because "
                    "the maximum number of open trades was "
                    "reached before broker validation."
                ),
            )

        checks.append(
            (
                "Final maximum open trades check passed: "
                f"{current_open_trades}/{max_open_trades}"
            )
        )

        # =========================================================
        # 9. FRESH BROKER VALIDATION
        # =========================================================

        try:

            validation = broker_validation_service.validate(
                symbol=intent.symbol,
                direction=direction,
                entry_price=intent.signal_entry_price,
                stop_loss=intent.stop_loss,
                take_profit=intent.take_profit,
                volume=intent.volume,
            )

        except Exception as exc:

            error_message = (
                "Fresh broker validation failed: "
                f"{exc}"
            )

            self._mark_rejected(
                db,
                intent,
                error_message,
            )

            return self._build_result(
                intent,
                approved=False,
                status="rejected",
                checks=checks,
                errors=[
                    "Fresh broker validation failed.",
                    str(exc),
                ],
                message=(
                    "Trade confirmation was rejected because "
                    "fresh broker validation could not be completed."
                ),
            )

        # =========================================================
        # 10. COLLECT BROKER DIAGNOSTICS
        # =========================================================

        checks.extend(
            getattr(
                validation,
                "checks",
                [],
            )
        )

        warnings.extend(
            getattr(
                validation,
                "warnings",
                [],
            )
        )

        if not validation.approved:

            validation_errors = getattr(
                validation,
                "errors",
                [],
            )

            errors.extend(validation_errors)

            error_message = (
                "; ".join(errors)
                if errors
                else (
                    "Fresh broker validation rejected "
                    "the trade."
                )
            )

            self._mark_rejected(
                db,
                intent,
                error_message,
            )

            return self._build_result(
                intent,
                approved=False,
                status="rejected",
                checks=checks,
                warnings=warnings,
                errors=errors,
                margin_required=getattr(
                    validation,
                    "margin_required",
                    None,
                ),
                free_margin=getattr(
                    validation,
                    "free_margin",
                    None,
                ),
                signal_price_deviation=getattr(
                    validation,
                    "signal_price_deviation",
                    None,
                ),
                signal_price_deviation_percent=getattr(
                    validation,
                    "signal_price_deviation_percent",
                    None,
                ),
                message=(
                    "Trade confirmation was rejected by "
                    "fresh broker validation."
                ),
            )

        checks.append(
            "Fresh broker validation passed"
        )

        # =========================================================
        # 11. REFRESH SERVER-SIDE BROKER INFORMATION
        # =========================================================

        intent.broker_symbol = getattr(
            validation,
            "broker_symbol",
            intent.broker_symbol,
        )

        intent.execution_price = getattr(
            validation,
            "execution_price",
            intent.execution_price,
        )

        intent.margin_required = getattr(
            validation,
            "margin_required",
            intent.margin_required,
        )

        intent.free_margin = getattr(
            validation,
            "free_margin",
            intent.free_margin,
        )

        validation_deviation_percent = getattr(
            validation,
            "signal_price_deviation_percent",
            None,
        )

        if validation_deviation_percent is not None:
            intent.signal_price_deviation_percent = (
                validation_deviation_percent
            )

        intent.updated_at = self._now()

        db.commit()
        db.refresh(intent)

        checks.extend(
            [
                "Server-side broker symbol refreshed",
                "Server-side execution price refreshed",
                "Server-side margin information refreshed",
            ]
        )

        # =========================================================
        # 12. FINAL MT5 OWNERSHIP RE-VERIFICATION
        # =========================================================

        try:
            self._get_verified_mt5_account(
                db,
                user_id,
            )

        except TradeConfirmationError as exc:
            error_message = str(exc)

            self._mark_rejected(
                db,
                intent,
                error_message,
            )

            return self._build_result(
                intent,
                approved=False,
                status="rejected",
                checks=checks,
                warnings=warnings,
                errors=[error_message],
                margin_required=intent.margin_required,
                free_margin=intent.free_margin,
                signal_price_deviation=getattr(
                    intent,
                    "signal_price_deviation",
                    None,
                ),
                signal_price_deviation_percent=getattr(
                    intent,
                    "signal_price_deviation_percent",
                    None,
                ),
                execution_sent=False,
                message=(
                    "MT5 execution was blocked because account "
                    "ownership could not be verified immediately "
                    "before order submission."
                ),
            )

        checks.append(
            "Final MT5 account ownership verification passed immediately before execution"
        )

        # =========================================================
        # 13. FINAL MT5 EXECUTION SERVICE
        # =========================================================

        try:

            execution_result = (
                mt5_execution_service.execute(
                    symbol=intent.symbol,
                    direction=direction,
                    volume=intent.volume,
                    signal_entry_price=(
                        intent.signal_entry_price
                    ),
                    stop_loss=intent.stop_loss,
                    take_profit=intent.take_profit,
                    risk_percent=intent.risk_percent,
                    confirmation=True,
                )
            )

        except Exception as exc:

            error_message = (
                "MT5 execution service failed unexpectedly: "
                f"{exc}"
            )

            self._mark_execution_unknown(
                db,
                intent,
                error_message,
            )

            return self._build_result(
                intent,
                approved=False,
                status="execution_unknown",
                checks=checks,
                warnings=warnings,
                errors=[
                    "MT5 execution service failed unexpectedly.",
                    str(exc),
                ],
                margin_required=intent.margin_required,
                free_margin=intent.free_margin,
                signal_price_deviation=getattr(
                    intent,
                    "signal_price_deviation",
                    None,
                ),
                signal_price_deviation_percent=getattr(
                    intent,
                    "signal_price_deviation_percent",
                    None,
                ),
                execution_sent=False,
                message=(
                    "MT5 execution could not be conclusively "
                    "determined. The trade has been placed into "
                    "execution-unknown status and must be "
                    "reconciled before another execution attempt."
                ),
            )

        # =========================================================
        # 14. COLLECT FINAL EXECUTION DIAGNOSTICS
        # =========================================================

        checks.extend(
            getattr(
                execution_result,
                "checks",
                [],
            )
        )

        warnings.extend(
            getattr(
                execution_result,
                "warnings",
                [],
            )
        )

        errors.extend(
            getattr(
                execution_result,
                "errors",
                [],
            )
        )

        # =========================================================
        # 15. PERSIST FINAL EXECUTION RESULT
        # =========================================================

        self._mark_execution_result(
            db,
            intent,
            execution_result,
        )

        # =========================================================
        # 16. RECONCILE SUCCESSFUL BROKER EXECUTION
        # =========================================================

        execution_approved = bool(
            getattr(
                execution_result,
                "approved",
                False,
            )
        )

        execution_sent = bool(
            getattr(
                execution_result,
                "execution_sent",
                False,
            )
        )

        if (
            execution_approved
            and execution_sent
            and getattr(
                execution_result,
                "execution_mode",
                getattr(intent, "execution_mode", "market"),
            ) == "pending"
        ):
            intent = self._load_owned_intent(
                db,
                intent.id,
                user_id,
            )

            if intent is None:
                raise TradeConfirmationError(
                    "Trade intent disappeared after pending order placement."
                )

            return self._build_result(
                intent,
                approved=True,
                status="pending_order_placed",
                checks=checks,
                warnings=warnings,
                errors=[],
                order_ticket=getattr(
                    execution_result,
                    "order_ticket",
                    intent.order_ticket,
                ),
                deal_ticket=None,
                retcode=getattr(
                    execution_result,
                    "retcode",
                    intent.retcode,
                ),
                retcode_description=getattr(
                    execution_result,
                    "retcode_description",
                    intent.retcode_description,
                ),
                margin_required=getattr(
                    execution_result,
                    "margin_required",
                    intent.margin_required,
                ),
                free_margin=getattr(
                    execution_result,
                    "free_margin",
                    intent.free_margin,
                ),
                risk_amount=getattr(
                    execution_result,
                    "risk_amount",
                    None,
                ),
                risk_percent=getattr(
                    execution_result,
                    "risk_percent",
                    intent.risk_percent,
                ),
                signal_price_deviation=None,
                signal_price_deviation_percent=None,
                execution_sent=True,
                message=(
                    "Pending order was accepted by MetaTrader 5 "
                    "and is waiting for activation."
                ),
            )

        if execution_approved and execution_sent:

            # The broker accepted the request, but this is NOT yet
            # considered a completed platform execution.
            #
            # The reconciliation service must prove the resulting
            # live MT5 position before TradeIntent becomes executed.

            reconciliation_result = (
                position_reconciliation_service.reconcile(
                    db=db,
                    user_id=user_id,
                    intent_id=intent.id,
                )
            )

            checks.extend(
                reconciliation_result.checks
            )

            warnings.extend(
                reconciliation_result.warnings
            )

            errors.extend(
                reconciliation_result.errors
            )

            if reconciliation_result.reconciled:

                intent = self._load_owned_intent(
                    db,
                    intent.id,
                    user_id,
                )

                if intent is None:
                    raise TradeConfirmationError(
                        "Trade intent disappeared during execution reconciliation."
                    )

                intent.execution_status = "executed"
                intent.execution_time = (
                    intent.execution_time
                    or self._now()
                )
                intent.error_message = None
                intent.updated_at = self._now()

                db.commit()
                db.refresh(intent)

                return self._build_result(
                    intent,
                    approved=True,
                    status="executed",
                    checks=checks,
                    warnings=warnings,
                    errors=[],
                    order_ticket=getattr(
                        execution_result,
                        "order_ticket",
                        intent.order_ticket,
                    ),
                    deal_ticket=getattr(
                        execution_result,
                        "deal_ticket",
                        intent.deal_ticket,
                    ),
                    retcode=getattr(
                        execution_result,
                        "retcode",
                        intent.retcode,
                    ),
                    retcode_description=getattr(
                        execution_result,
                        "retcode_description",
                        intent.retcode_description,
                    ),
                    margin_required=getattr(
                        execution_result,
                        "margin_required",
                        intent.margin_required,
                    ),
                    free_margin=getattr(
                        execution_result,
                        "free_margin",
                        intent.free_margin,
                    ),
                    risk_amount=getattr(
                        execution_result,
                        "risk_amount",
                        None,
                    ),
                    risk_percent=getattr(
                        execution_result,
                        "risk_percent",
                        intent.risk_percent,
                    ),
                    signal_price_deviation=getattr(
                        execution_result,
                        "signal_price_deviation",
                        None,
                    ),
                    signal_price_deviation_percent=getattr(
                        execution_result,
                        "signal_price_deviation_percent",
                        intent.signal_price_deviation_percent,
                    ),
                    execution_sent=True,
                    message=(
                        "Trade was accepted by MetaTrader 5 and "
                        "successfully reconciled with the live position."
                    ),
                )

            # Broker accepted the execution, but we cannot prove the
            # resulting live position. Never report success and never
            # automatically retry.
            intent = self._load_owned_intent(
                db,
                intent.id,
                user_id,
            )

            if intent is None:
                raise TradeConfirmationError(
                    "Trade intent disappeared during reconciliation."
                )

            intent.execution_status = (
                "execution_reconciliation_required"
            )

            intent.error_message = (
                reconciliation_result.message
            )

            intent.updated_at = self._now()

            db.commit()
            db.refresh(intent)

            return self._build_result(
                intent,
                approved=False,
                status="execution_reconciliation_required",
                checks=checks,
                warnings=warnings,
                errors=errors,
                order_ticket=getattr(
                    execution_result,
                    "order_ticket",
                    intent.order_ticket,
                ),
                deal_ticket=getattr(
                    execution_result,
                    "deal_ticket",
                    intent.deal_ticket,
                ),
                retcode=getattr(
                    execution_result,
                    "retcode",
                    intent.retcode,
                ),
                retcode_description=getattr(
                    execution_result,
                    "retcode_description",
                    intent.retcode_description,
                ),
                margin_required=getattr(
                    execution_result,
                    "margin_required",
                    intent.margin_required,
                ),
                free_margin=getattr(
                    execution_result,
                    "free_margin",
                    intent.free_margin,
                ),
                risk_amount=getattr(
                    execution_result,
                    "risk_amount",
                    None,
                ),
                risk_percent=getattr(
                    execution_result,
                    "risk_percent",
                    intent.risk_percent,
                ),
                signal_price_deviation=getattr(
                    execution_result,
                    "signal_price_deviation",
                    None,
                ),
                signal_price_deviation_percent=getattr(
                    execution_result,
                    "signal_price_deviation_percent",
                    intent.signal_price_deviation_percent,
                ),
                execution_sent=True,
                message=(
                    "MetaTrader 5 accepted the execution request, "
                    "but the resulting live position could not be "
                    "safely proven. The execution is locked pending "
                    "reconciliation. No automatic retry will occur."
                ),
            )

        # =========================================================
        # 15. MT5 EXECUTION REJECTED
        # =========================================================

        return self._build_result(
            intent,
            approved=False,
            status="rejected",
            checks=checks,
            warnings=warnings,
            errors=errors,
            order_ticket=getattr(
                execution_result,
                "order_ticket",
                None,
            ),
            deal_ticket=getattr(
                execution_result,
                "deal_ticket",
                None,
            ),
            retcode=getattr(
                execution_result,
                "retcode",
                None,
            ),
            retcode_description=getattr(
                execution_result,
                "retcode_description",
                None,
            ),
            margin_required=getattr(
                execution_result,
                "margin_required",
                intent.margin_required,
            ),
            free_margin=getattr(
                execution_result,
                "free_margin",
                intent.free_margin,
            ),
            risk_amount=getattr(
                execution_result,
                "risk_amount",
                None,
            ),
            risk_percent=getattr(
                execution_result,
                "risk_percent",
                intent.risk_percent,
            ),
            signal_price_deviation=getattr(
                execution_result,
                "signal_price_deviation",
                None,
            ),
            signal_price_deviation_percent=getattr(
                execution_result,
                "signal_price_deviation_percent",
                intent.signal_price_deviation_percent,
            ),
            execution_sent=execution_sent,
            message=(
                "Trade confirmation was received, but "
                "MetaTrader 5 did not successfully "
                "execute the trade."
            ),
        )


trade_confirmation_service = TradeConfirmationService()
