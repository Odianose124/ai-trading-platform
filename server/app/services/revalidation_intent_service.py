from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.trade_intent import TradeIntent
from app.services.trade_intent_service import (
    TradeIntentError,
    trade_intent_service,
)
from app.services.trade_revalidation_service import (
    TradeRevalidationError,
    trade_revalidation_service,
)


class RevalidationIntentError(Exception):
    """Raised when a revalidation-to-intent operation cannot be completed."""


@dataclass
class RevalidationIntentResult:
    approved: bool
    status: str
    original_intent_id: int | None
    new_intent_id: int | None
    user_id: int | None
    symbol: str | None
    broker_symbol: str | None
    direction: str | None
    volume: Decimal | None
    original_signal_entry_price: Decimal | None
    revalidated_entry_price: Decimal | None
    execution_price: Decimal | None
    stop_loss: Decimal | None
    take_profit: Decimal | None
    risk_percent: Decimal | None
    signal_price_deviation_percent: Decimal | None
    expires_at: datetime | None
    checks: list[str]
    warnings: list[str]
    errors: list[str]
    message: str

    def serialize(self) -> dict:
        return {
            "approved": self.approved,
            "status": self.status,
            "original_intent_id": self.original_intent_id,
            "new_intent_id": self.new_intent_id,
            "user_id": self.user_id,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "direction": self.direction,
            "volume": (
                float(self.volume)
                if self.volume is not None
                else None
            ),
            "original_signal_entry_price": (
                float(self.original_signal_entry_price)
                if self.original_signal_entry_price is not None
                else None
            ),
            "revalidated_entry_price": (
                float(self.revalidated_entry_price)
                if self.revalidated_entry_price is not None
                else None
            ),
            "execution_price": (
                float(self.execution_price)
                if self.execution_price is not None
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
            "risk_percent": (
                float(self.risk_percent)
                if self.risk_percent is not None
                else None
            ),
            "signal_price_deviation_percent": (
                float(self.signal_price_deviation_percent)
                if self.signal_price_deviation_percent is not None
                else None
            ),
            "expires_at": (
                self.expires_at.isoformat()
                if self.expires_at is not None
                else None
            ),
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "message": self.message,
        }


class RevalidationIntentService:
    """
    Converts a fresh trade revalidation into a NEW trade intent.

    Safety rules:

    - Existing intents are never silently modified.
    - Fresh market values are used only for the NEW intent.
    - No MT5 order is sent.
    - The new intent remains pending confirmation.
    - The original intent remains available for audit/history.
    """

    def _to_decimal(
        self,
        value: Any,
        field_name: str,
    ) -> Decimal:
        try:
            result = Decimal(str(value))
        except Exception as exc:
            raise RevalidationIntentError(
                f"{field_name} must be a valid number."
            ) from exc

        if not result.is_finite():
            raise RevalidationIntentError(
                f"{field_name} must be finite."
            )

        return result

    def _extract(
        self,
        source: Any,
        key: str,
        default=None,
    ):
        if source is None:
            return default

        if isinstance(source, dict):
            return source.get(key, default)

        return getattr(source, key, default)

    def _extract_first(
        self,
        source: Any,
        keys: tuple[str, ...],
        default=None,
    ):
        for key in keys:
            value = self._extract(
                source,
                key,
                None,
            )

            if value is not None:
                return value

        return default

    def _build_failure(
        self,
        *,
        original_intent: TradeIntent | None,
        status: str,
        checks: list[str] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        message: str,
        revalidated_entry_price=None,
        execution_price=None,
        stop_loss=None,
        take_profit=None,
        volume=None,
        risk_percent=None,
        signal_price_deviation_percent=None,
    ) -> RevalidationIntentResult:
        return RevalidationIntentResult(
            approved=False,
            status=status,
            original_intent_id=(
                original_intent.id
                if original_intent is not None
                else None
            ),
            new_intent_id=None,
            user_id=(
                original_intent.user_id
                if original_intent is not None
                else None
            ),
            symbol=(
                original_intent.symbol
                if original_intent is not None
                else None
            ),
            broker_symbol=(
                original_intent.broker_symbol
                if original_intent is not None
                else None
            ),
            direction=(
                original_intent.direction
                if original_intent is not None
                else None
            ),
            volume=volume,
            original_signal_entry_price=(
                original_intent.signal_entry_price
                if original_intent is not None
                else None
            ),
            revalidated_entry_price=revalidated_entry_price,
            execution_price=execution_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_percent=risk_percent,
            signal_price_deviation_percent=(
                signal_price_deviation_percent
            ),
            expires_at=None,
            checks=checks or [],
            warnings=warnings or [],
            errors=errors or [],
            message=message,
        )

    def revalidate_and_create(
        self,
        db: Session,
        *,
        intent_id: int,
        user_id: int,
    ) -> RevalidationIntentResult:
        checks: list[str] = []
        warnings: list[str] = []

        # =========================================================
        # 1. Validate request
        # =========================================================

        if intent_id <= 0:
            return self._build_failure(
                original_intent=None,
                status="invalid_request",
                errors=[
                    "Intent ID must be greater than zero."
                ],
                message=(
                    "Trade revalidation request is invalid."
                ),
            )

        if user_id is None:
            return self._build_failure(
                original_intent=None,
                status="authentication_required",
                errors=[
                    "Authenticated user is required."
                ],
                message=(
                    "Trade revalidation requires "
                    "an authenticated user."
                ),
            )

        checks.append(
            "Revalidation-to-intent request parameters verified"
        )

        # =========================================================
        # 2. Load original intent
        # =========================================================

        original_intent = (
            db.query(TradeIntent)
            .filter(
                TradeIntent.id == intent_id,
                TradeIntent.user_id == user_id,
            )
            .first()
        )

        if original_intent is None:
            return self._build_failure(
                original_intent=None,
                status="not_found",
                errors=[
                    "Trade intent not found."
                ],
                message=(
                    "The requested trade intent was not found."
                ),
            )

        checks.append(
            "Authenticated user ownership verified"
        )

        # =========================================================
        # 3. Verify confirmation status
        # =========================================================

        if original_intent.confirmation_status != "pending":
            return self._build_failure(
                original_intent=original_intent,
                status="already_processed",
                checks=checks,
                errors=[
                    (
                        "Original trade intent is no longer "
                        "pending confirmation."
                    )
                ],
                message=(
                    "The original trade intent has already "
                    "been processed and cannot be revalidated."
                ),
            )

        checks.append(
            "Original trade intent is still pending confirmation"
        )

        # =========================================================
        # 4. Verify execution status
        # =========================================================

        if original_intent.execution_status != "not_executed":
            return self._build_failure(
                original_intent=original_intent,
                status="already_processed",
                checks=checks,
                errors=[
                    (
                        "Original trade intent execution "
                        "has already been processed."
                    )
                ],
                message=(
                    "The original trade intent is no longer "
                    "eligible for revalidation."
                ),
            )

        checks.append(
            "Original trade intent has not been executed"
        )

        # =========================================================
        # 5. Verify expiration
        # =========================================================

        if original_intent.expires_at is not None:
            expires_at = original_intent.expires_at

            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(
                    tzinfo=timezone.utc
                )

            now = datetime.now(timezone.utc)

            if now >= expires_at:
                original_intent.confirmation_status = "expired"
                original_intent.execution_status = "blocked"
                original_intent.error_message = (
                    "Trade intent expired before revalidation."
                )
                original_intent.updated_at = now

                db.commit()
                db.refresh(original_intent)

                return self._build_failure(
                    original_intent=original_intent,
                    status="expired",
                    checks=checks,
                    errors=[
                        (
                            "Original trade intent expired "
                            "before revalidation."
                        )
                    ],
                    message=(
                        "The original trade intent has expired "
                        "and cannot be revalidated."
                    ),
                )

            checks.append(
                "Original trade intent expiration verified"
            )

        # =========================================================
        # 6. Fresh trade revalidation
        #
        # IMPORTANT:
        # TradeRevalidationService.revalidate() is keyword-only.
        #
        # It does NOT receive:
        #     db
        #     user_id
        #
        # It receives the original trade values and then performs
        # fresh MT5-based market validation.
        #
        # It does NOT call mt5.order_send().
        # =========================================================

        try:
            revalidation = (
                trade_revalidation_service.revalidate(
                    intent_id=original_intent.id,
                    symbol=original_intent.symbol,
                    direction=original_intent.direction,
                    original_signal_entry_price=(
                        original_intent.signal_entry_price
                    ),
                    original_stop_loss=(
                        original_intent.stop_loss
                    ),
                    original_take_profit=(
                        original_intent.take_profit
                    ),
                    risk_percent=(
                        original_intent.risk_percent
                    ),
                    volume=(
                        original_intent.volume
                    ),
                    timeframe="15m",
                    limit=500,
                    strength=2,
                    lookback=20,
                    minimum_touches=2,
                )
            )

        except TradeRevalidationError as exc:
            return self._build_failure(
                original_intent=original_intent,
                status="revalidation_failed",
                checks=checks,
                warnings=warnings,
                errors=[
                    f"Fresh trade revalidation failed: {exc}"
                ],
                message=(
                    "Fresh trade revalidation could not "
                    "be completed safely."
                ),
            )

        except Exception as exc:
            return self._build_failure(
                original_intent=original_intent,
                status="revalidation_failed",
                checks=checks,
                warnings=warnings,
                errors=[
                    f"Fresh trade revalidation failed: {exc}"
                ],
                message=(
                    "Fresh trade revalidation could not "
                    "be completed safely."
                ),
            )

        # =========================================================
        # 7. Check fresh revalidation result
        # =========================================================

        revalidation_approved = bool(
            self._extract(
                revalidation,
                "approved",
                False,
            )
        )

        if not revalidation_approved:
            return self._build_failure(
                original_intent=original_intent,
                status=str(
                    self._extract(
                        revalidation,
                        "status",
                        "revalidation_failed",
                    )
                ),
                checks=(
                    checks
                    + list(
                        self._extract(
                            revalidation,
                            "checks",
                            [],
                        )
                        or []
                    )
                ),
                warnings=(
                    warnings
                    + list(
                        self._extract(
                            revalidation,
                            "warnings",
                            [],
                        )
                        or []
                    )
                ),
                errors=list(
                    self._extract(
                        revalidation,
                        "errors",
                        [
                            (
                                "Fresh trade revalidation "
                                "was rejected."
                            )
                        ],
                    )
                    or []
                ),
                message=str(
                    self._extract(
                        revalidation,
                        "message",
                        (
                            "Fresh trade revalidation "
                            "was rejected."
                        ),
                    )
                ),
            )

        checks.append(
            "Fresh trade revalidation approved"
        )

        # =========================================================
        # 8. Extract fresh values
        # =========================================================

        fresh_symbol = self._extract_first(
            revalidation,
            ("symbol",),
            original_intent.symbol,
        )

        fresh_broker_symbol = self._extract_first(
            revalidation,
            ("broker_symbol",),
            original_intent.broker_symbol,
        )

        fresh_direction = self._extract_first(
            revalidation,
            ("direction",),
            original_intent.direction,
        )

        fresh_entry = self._extract_first(
            revalidation,
            (
                "entry_price",
                "revalidated_entry_price",
            ),
        )

        fresh_execution_price = self._extract_first(
            revalidation,
            (
                "execution_price",
                "current_execution_price",
            ),
        )

        fresh_stop_loss = self._extract(
            revalidation,
            "stop_loss",
        )

        fresh_take_profit = self._extract_first(
            revalidation,
            (
                "take_profit",
                "take_profit_1",
            ),
        )

        fresh_volume = self._extract(
            revalidation,
            "volume",
        )

        fresh_risk_percent = self._extract(
            revalidation,
            "risk_percent",
            original_intent.risk_percent,
        )

        fresh_deviation = self._extract(
            revalidation,
            "signal_price_deviation_percent",
        )

        # =========================================================
        # 9. Required fresh values
        # =========================================================

        if fresh_entry is None:
            return self._build_failure(
                original_intent=original_intent,
                status="invalid_revalidation",
                checks=checks,
                warnings=warnings,
                errors=[
                    (
                        "Fresh revalidation did not "
                        "return an entry price."
                    )
                ],
                message=(
                    "Fresh revalidation succeeded but did not "
                    "return a usable entry price."
                ),
            )

        if fresh_execution_price is None:
            fresh_execution_price = fresh_entry

        if fresh_stop_loss is None:
            return self._build_failure(
                original_intent=original_intent,
                status="invalid_revalidation",
                checks=checks,
                warnings=warnings,
                errors=[
                    (
                        "Fresh revalidation did not "
                        "return a stop loss."
                    )
                ],
                message=(
                    "Fresh revalidation did not provide "
                    "a usable stop loss."
                ),
            )

        if fresh_take_profit is None:
            return self._build_failure(
                original_intent=original_intent,
                status="invalid_revalidation",
                checks=checks,
                warnings=warnings,
                errors=[
                    (
                        "Fresh revalidation did not "
                        "return take profit."
                    )
                ],
                message=(
                    "Fresh revalidation did not provide "
                    "a usable take-profit level."
                ),
            )

        if fresh_volume is None:
            return self._build_failure(
                original_intent=original_intent,
                status="invalid_revalidation",
                checks=checks,
                warnings=warnings,
                errors=[
                    (
                        "Fresh revalidation did not "
                        "return a position size."
                    )
                ],
                message=(
                    "Fresh revalidation did not provide "
                    "a usable position size."
                ),
            )

        # =========================================================
        # 10. Convert numeric values
        # =========================================================

        fresh_entry = self._to_decimal(
            fresh_entry,
            "Fresh entry price",
        )

        fresh_execution_price = self._to_decimal(
            fresh_execution_price,
            "Fresh execution price",
        )

        fresh_stop_loss = self._to_decimal(
            fresh_stop_loss,
            "Fresh stop loss",
        )

        fresh_take_profit = self._to_decimal(
            fresh_take_profit,
            "Fresh take profit",
        )

        fresh_volume = self._to_decimal(
            fresh_volume,
            "Fresh volume",
        )

        if fresh_risk_percent is not None:
            fresh_risk_percent = self._to_decimal(
                fresh_risk_percent,
                "Fresh risk percent",
            )

        if fresh_deviation is not None:
            fresh_deviation = self._to_decimal(
                fresh_deviation,
                "Fresh signal price deviation percent",
            )

        # =========================================================
        # 11. Verify volume
        # =========================================================

        if fresh_volume <= 0:
            return self._build_failure(
                original_intent=original_intent,
                status="invalid_revalidation",
                checks=checks,
                errors=[
                    (
                        "Fresh position volume must be "
                        "greater than zero."
                    )
                ],
                message=(
                    "Fresh position sizing returned "
                    "an invalid volume."
                ),
                revalidated_entry_price=fresh_entry,
                execution_price=fresh_execution_price,
                stop_loss=fresh_stop_loss,
                take_profit=fresh_take_profit,
                volume=fresh_volume,
                risk_percent=fresh_risk_percent,
                signal_price_deviation_percent=fresh_deviation,
            )

        # =========================================================
        # 12. Verify direction
        # =========================================================

        normalized_direction = str(
            fresh_direction
        ).strip().lower()

        if normalized_direction not in {
            "buy",
            "sell",
            "long",
            "short",
        }:
            return self._build_failure(
                original_intent=original_intent,
                status="invalid_revalidation",
                checks=checks,
                errors=[
                    (
                        "Fresh revalidation returned "
                        "an invalid trade direction."
                    )
                ],
                message=(
                    "Fresh trade direction is invalid."
                ),
                revalidated_entry_price=fresh_entry,
                execution_price=fresh_execution_price,
                stop_loss=fresh_stop_loss,
                take_profit=fresh_take_profit,
                volume=fresh_volume,
                risk_percent=fresh_risk_percent,
                signal_price_deviation_percent=fresh_deviation,
            )

        # =========================================================
        # 13. Normalize direction and validate geometry
        # =========================================================

        if normalized_direction in {
            "long",
            "buy",
        }:
            normalized_direction = "buy"

            if fresh_stop_loss >= fresh_execution_price:
                return self._build_failure(
                    original_intent=original_intent,
                    status="invalid_revalidation",
                    checks=checks,
                    errors=[
                        (
                            "Fresh BUY stop loss must be "
                            "below execution price."
                        )
                    ],
                    message=(
                        "Fresh BUY trade geometry is invalid."
                    ),
                    revalidated_entry_price=fresh_entry,
                    execution_price=fresh_execution_price,
                    stop_loss=fresh_stop_loss,
                    take_profit=fresh_take_profit,
                    volume=fresh_volume,
                    risk_percent=fresh_risk_percent,
                    signal_price_deviation_percent=fresh_deviation,
                )

            if fresh_take_profit <= fresh_execution_price:
                return self._build_failure(
                    original_intent=original_intent,
                    status="invalid_revalidation",
                    checks=checks,
                    errors=[
                        (
                            "Fresh BUY take profit must be "
                            "above execution price."
                        )
                    ],
                    message=(
                        "Fresh BUY trade geometry is invalid."
                    ),
                    revalidated_entry_price=fresh_entry,
                    execution_price=fresh_execution_price,
                    stop_loss=fresh_stop_loss,
                    take_profit=fresh_take_profit,
                    volume=fresh_volume,
                    risk_percent=fresh_risk_percent,
                    signal_price_deviation_percent=fresh_deviation,
                )

        else:
            normalized_direction = "sell"

            if fresh_stop_loss <= fresh_execution_price:
                return self._build_failure(
                    original_intent=original_intent,
                    status="invalid_revalidation",
                    checks=checks,
                    errors=[
                        (
                            "Fresh SELL stop loss must be "
                            "above execution price."
                        )
                    ],
                    message=(
                        "Fresh SELL trade geometry is invalid."
                    ),
                    revalidated_entry_price=fresh_entry,
                    execution_price=fresh_execution_price,
                    stop_loss=fresh_stop_loss,
                    take_profit=fresh_take_profit,
                    volume=fresh_volume,
                    risk_percent=fresh_risk_percent,
                    signal_price_deviation_percent=fresh_deviation,
                )

            if fresh_take_profit >= fresh_execution_price:
                return self._build_failure(
                    original_intent=original_intent,
                    status="invalid_revalidation",
                    checks=checks,
                    errors=[
                        (
                            "Fresh SELL take profit must be "
                            "below execution price."
                        )
                    ],
                    message=(
                        "Fresh SELL trade geometry is invalid."
                    ),
                    revalidated_entry_price=fresh_entry,
                    execution_price=fresh_execution_price,
                    stop_loss=fresh_stop_loss,
                    take_profit=fresh_take_profit,
                    volume=fresh_volume,
                    risk_percent=fresh_risk_percent,
                    signal_price_deviation_percent=fresh_deviation,
                )

        checks.append(
            "Fresh revalidated trade geometry verified"
        )

        # =========================================================
        # 14. Preserve original intent
        # =========================================================

        if (
            fresh_entry != original_intent.signal_entry_price
            or fresh_stop_loss != original_intent.stop_loss
            or fresh_take_profit != original_intent.take_profit
            or fresh_volume != original_intent.volume
        ):
            warnings.append(
                (
                    "Fresh market revalidation produced "
                    "updated trade values. The original "
                    "intent will remain unchanged."
                )
            )

        checks.append(
            "Original intent values preserved for audit"
        )

        # =========================================================
        # 15. Create NEW trade intent
        #
        # No MT5 execution occurs here.
        # =========================================================

        try:
            new_intent = trade_intent_service.create(
                db=db,
                user_id=user_id,
                symbol=str(
                    fresh_symbol
                ).strip().upper(),
                broker_symbol=str(
                    fresh_broker_symbol or ""
                ).strip(),
                direction=normalized_direction,
                volume=fresh_volume,
                signal_entry_price=fresh_entry,
                execution_price=fresh_execution_price,
                stop_loss=fresh_stop_loss,
                take_profit=fresh_take_profit,
                risk_percent=fresh_risk_percent,
                signal_price_deviation_percent=fresh_deviation,
                margin_required=self._extract(
                    revalidation,
                    "margin_required",
                ),
                free_margin=self._extract(
                    revalidation,
                    "free_margin",
                ),
                preview_status="ready_for_confirmation",
                warnings=warnings,
            )

        except TradeIntentError as exc:
            db.rollback()

            return self._build_failure(
                original_intent=original_intent,
                status="intent_creation_failed",
                checks=checks,
                warnings=warnings,
                errors=[
                    str(exc)
                ],
                message=(
                    "Fresh revalidation passed, but the "
                    "new trade intent could not be created."
                ),
                revalidated_entry_price=fresh_entry,
                execution_price=fresh_execution_price,
                stop_loss=fresh_stop_loss,
                take_profit=fresh_take_profit,
                volume=fresh_volume,
                risk_percent=fresh_risk_percent,
                signal_price_deviation_percent=fresh_deviation,
            )

        except Exception as exc:
            db.rollback()

            return self._build_failure(
                original_intent=original_intent,
                status="intent_creation_failed",
                checks=checks,
                warnings=warnings,
                errors=[
                    (
                        "New trade intent creation failed: "
                        f"{exc}"
                    )
                ],
                message=(
                    "Fresh revalidation passed, but the "
                    "new trade intent could not be created."
                ),
                revalidated_entry_price=fresh_entry,
                execution_price=fresh_execution_price,
                stop_loss=fresh_stop_loss,
                take_profit=fresh_take_profit,
                volume=fresh_volume,
                risk_percent=fresh_risk_percent,
                signal_price_deviation_percent=fresh_deviation,
            )

        # =========================================================
        # 16. Extract new intent values
        # =========================================================

        new_intent_id = self._extract(
            new_intent,
            "intent_id",
        )

        new_expires_at = self._extract(
            new_intent,
            "expires_at",
        )

        new_broker_symbol = self._extract(
            new_intent,
            "broker_symbol",
            fresh_broker_symbol,
        )

        new_volume = self._extract(
            new_intent,
            "volume",
            fresh_volume,
        )

        new_execution_price = self._extract(
            new_intent,
            "execution_price",
            fresh_execution_price,
        )

        new_deviation = self._extract(
            new_intent,
            "signal_price_deviation_percent",
            fresh_deviation,
        )

        checks.append(
            "New trade intent created from fresh revalidated values"
        )

        checks.append(
            "New trade intent remains pending confirmation"
        )

        checks.append(
            "No MT5 execution requested"
        )

        # =========================================================
        # 17. Return successful result
        # =========================================================

        return RevalidationIntentResult(
            approved=True,
            status="new_intent_created",
            original_intent_id=original_intent.id,
            new_intent_id=(
                int(new_intent_id)
                if new_intent_id is not None
                else None
            ),
            user_id=user_id,
            symbol=str(
                fresh_symbol
            ).strip().upper(),
            broker_symbol=str(
                new_broker_symbol
                or fresh_broker_symbol
                or ""
            ).strip(),
            direction=normalized_direction,
            volume=(
                self._to_decimal(
                    new_volume,
                    "New intent volume",
                )
                if new_volume is not None
                else fresh_volume
            ),
            original_signal_entry_price=(
                original_intent.signal_entry_price
            ),
            revalidated_entry_price=fresh_entry,
            execution_price=(
                self._to_decimal(
                    new_execution_price,
                    "New intent execution price",
                )
                if new_execution_price is not None
                else fresh_execution_price
            ),
            stop_loss=fresh_stop_loss,
            take_profit=fresh_take_profit,
            risk_percent=fresh_risk_percent,
            signal_price_deviation_percent=(
                self._to_decimal(
                    new_deviation,
                    "New intent signal deviation",
                )
                if new_deviation is not None
                else fresh_deviation
            ),
            expires_at=new_expires_at,
            checks=checks,
            warnings=(
                warnings
                + list(
                    self._extract(
                        new_intent,
                        "warnings",
                        [],
                    )
                    or []
                )
            ),
            errors=[],
            message=(
                "Fresh market revalidation passed and a new "
                "trade intent was created. The original intent "
                "remains unchanged. No MT5 order has been sent. "
                "Final confirmation is required for the new intent."
            ),
        )


revalidation_intent_service = RevalidationIntentService()