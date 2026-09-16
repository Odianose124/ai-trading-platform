from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.execution.position_manager import PositionManager
from app.models.management_profile import ManagementProfile
from app.models.managed_position import ManagedPosition
from app.models.mt5_trading_account import MT5TradingAccount
from app.mt5.connection import (
    MT5AccountMismatchError,
    MT5ConnectionError,
    mt5_connection,
)


class AITradeManagementError(Exception):
    """Raised when a management evaluation cannot be completed."""


@dataclass
class AITradeManagementResult:
    evaluated: bool
    status: str
    decision: str
    user_id: int | None
    managed_position_id: int | None
    position_ticket: int | None
    broker_symbol: str | None
    direction: str | None
    volume: Decimal | None
    entry_price: Decimal | None
    current_price: Decimal | None
    stop_loss: Decimal | None
    take_profit: Decimal | None
    profit_loss: Decimal | None
    initial_risk_distance: Decimal | None
    current_r: Decimal | None
    proposed_stop_loss: Decimal | None
    partial_close_percent: Decimal | None
    management_profile_id: int | None
    profile_name: str | None
    ai_management_enabled: bool
    checks: list[str]
    warnings: list[str]
    errors: list[str]
    message: str

    def serialize(self) -> dict:
        return {
            "evaluated": self.evaluated,
            "status": self.status,
            "decision": self.decision,
            "user_id": self.user_id,
            "managed_position_id": self.managed_position_id,
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
            "profit_loss": (
                float(self.profit_loss)
                if self.profit_loss is not None
                else None
            ),
            "initial_risk_distance": (
                float(self.initial_risk_distance)
                if self.initial_risk_distance is not None
                else None
            ),
            "current_r": (
                float(self.current_r)
                if self.current_r is not None
                else None
            ),
            "proposed_stop_loss": (
                float(self.proposed_stop_loss)
                if self.proposed_stop_loss is not None
                else None
            ),
            "partial_close_percent": (
                float(self.partial_close_percent)
                if self.partial_close_percent is not None
                else None
            ),
            "management_profile_id": self.management_profile_id,
            "profile_name": self.profile_name,
            "ai_management_enabled": self.ai_management_enabled,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "message": self.message,
        }


class AITradeManagementService:
    DECISION_HOLD = "HOLD"
    DECISION_MOVE_SL = "MOVE_SL"
    DECISION_PARTIAL_CLOSE = "PARTIAL_CLOSE"
    DECISION_CLOSE_POSITION = "CLOSE_POSITION"

    def __init__(self) -> None:
        self.position_manager = PositionManager()

    def _get_verified_mt5_account(
        self,
        db: Session,
        user_id: int,
    ) -> MT5TradingAccount:
        account = (
            db.query(MT5TradingAccount)
            .filter(
                MT5TradingAccount.user_id == user_id,
                MT5TradingAccount.is_active.is_(True),
            )
            .first()
        )

        if account is None:
            raise AITradeManagementError(
                "No active MT5 trading account is registered "
                "for this user."
            )

        try:
            mt5_connection.verify_account(
                expected_login=account.mt5_login,
                expected_server=account.server,
            )

        except MT5AccountMismatchError as exc:
            raise AITradeManagementError(
                str(exc)
            ) from exc

        except MT5ConnectionError as exc:
            raise AITradeManagementError(
                str(exc)
            ) from exc

        return account

    def _result(
        self,
        *,
        managed_position: ManagedPosition | None,
        profile: ManagementProfile | None,
        evaluated: bool,
        status: str,
        decision: str,
        user_id: int | None,
        current_position: dict | None = None,
        current_r: Decimal | None = None,
        proposed_stop_loss: Decimal | None = None,
        partial_close_percent: Decimal | None = None,
        checks: list[str] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        message: str = "",
    ) -> AITradeManagementResult:
        position = current_position or {}

        return AITradeManagementResult(
            evaluated=evaluated,
            status=status,
            decision=decision,
            user_id=user_id,
            managed_position_id=(
                managed_position.id
                if managed_position is not None
                else None
            ),
            position_ticket=(
                managed_position.position_ticket
                if managed_position is not None
                else position.get("ticket")
            ),
            broker_symbol=(
                managed_position.broker_symbol
                if managed_position is not None
                else position.get("symbol")
            ),
            direction=(
                managed_position.direction
                if managed_position is not None
                else position.get("type")
            ),
            volume=(
                Decimal(str(position["volume"]))
                if position.get("volume") is not None
                else (
                    managed_position.volume
                    if managed_position is not None
                    else None
                )
            ),
            entry_price=(
                Decimal(str(position["entry_price"]))
                if position.get("entry_price") is not None
                else (
                    managed_position.entry_price
                    if managed_position is not None
                    else None
                )
            ),
            current_price=(
                Decimal(str(position["current_price"]))
                if position.get("current_price") is not None
                else None
            ),
            stop_loss=(
                Decimal(str(position["stop_loss"]))
                if position.get("stop_loss") is not None
                else None
            ),
            take_profit=(
                Decimal(str(position["take_profit"]))
                if position.get("take_profit") is not None
                else None
            ),
            profit_loss=(
                Decimal(str(position["profit"]))
                if position.get("profit") is not None
                else (
                    managed_position.profit_loss
                    if managed_position is not None
                    else None
                )
            ),
            initial_risk_distance=(
                managed_position.initial_risk_distance
                if managed_position is not None
                else None
            ),
            current_r=current_r,
            proposed_stop_loss=proposed_stop_loss,
            partial_close_percent=partial_close_percent,
            management_profile_id=(
                profile.id
                if profile is not None
                else None
            ),
            profile_name=(
                profile.profile_name
                if profile is not None
                else None
            ),
            ai_management_enabled=(
                bool(profile.ai_management_enabled)
                if profile is not None
                else False
            ),
            checks=checks or [],
            warnings=warnings or [],
            errors=errors or [],
            message=message,
        )

    def _calculate_current_r(
        self,
        direction: str,
        entry_price: Decimal,
        current_price: Decimal,
        initial_risk_distance: Decimal,
    ) -> Decimal:
        if initial_risk_distance <= 0:
            raise AITradeManagementError(
                "Initial risk distance must be greater than zero."
            )

        if direction == "buy":
            return (
                current_price - entry_price
            ) / initial_risk_distance

        if direction == "sell":
            return (
                entry_price - current_price
            ) / initial_risk_distance

        raise AITradeManagementError(
            "Managed position direction is invalid."
        )

    def _is_stop_loss_improvement(
        self,
        direction: str,
        current_stop_loss: Decimal | None,
        proposed_stop_loss: Decimal,
    ) -> bool:
        if current_stop_loss is None:
            return True

        if direction == "buy":
            return proposed_stop_loss > current_stop_loss

        if direction == "sell":
            return proposed_stop_loss < current_stop_loss

        return False

    def _does_stop_reduce_risk(
        self,
        direction: str,
        entry_price: Decimal,
        initial_stop_loss: Decimal | None,
        proposed_stop_loss: Decimal,
    ) -> bool:
        if initial_stop_loss is None:
            return False

        if direction == "buy":
            original_distance = (
                entry_price - initial_stop_loss
            )
            proposed_distance = (
                entry_price - proposed_stop_loss
            )

        elif direction == "sell":
            original_distance = (
                initial_stop_loss - entry_price
            )
            proposed_distance = (
                proposed_stop_loss - entry_price
            )

        else:
            return False

        return proposed_distance <= original_distance

    def _validate_stop_loss_geometry(
        self,
        direction: str,
        current_price: Decimal,
        proposed_stop_loss: Decimal,
    ) -> bool:
        if direction == "buy":
            return proposed_stop_loss < current_price

        if direction == "sell":
            return proposed_stop_loss > current_price

        return False

    def _evaluate_stop_rules(
        self,
        managed_position: ManagedPosition,
        profile: ManagementProfile,
        current_position: dict,
        current_r: Decimal,
        checks: list[str],
        warnings: list[str],
    ) -> tuple[
        str,
        Decimal | None,
        Decimal | None,
    ]:
        direction = managed_position.direction

        entry_price = Decimal(
            str(managed_position.entry_price)
        )

        current_price = Decimal(
            str(current_position["current_price"])
        )

        current_stop_loss = (
            Decimal(str(current_position["stop_loss"]))
            if current_position.get("stop_loss") is not None
            else None
        )

        initial_stop_loss = (
            Decimal(str(managed_position.initial_stop_loss))
            if managed_position.initial_stop_loss is not None
            else None
        )

        candidates: list[
            tuple[str, Decimal]
        ] = []

        if (
            profile.break_even_enabled
            and profile.break_even_trigger_r is not None
            and profile.break_even_offset is not None
            and current_r >= Decimal(
                str(profile.break_even_trigger_r)
            )
        ):
            offset = Decimal(
                str(profile.break_even_offset)
            )

            if direction == "buy":
                target = entry_price + offset
            else:
                target = entry_price - offset

            candidates.append(
                ("break-even", target)
            )

            checks.append(
                "Break-even trigger is configured and reached"
            )

        if (
            profile.profit_protection_enabled
            and profile.profit_protection_trigger_r is not None
            and profile.locked_profit_r is not None
            and current_r >= Decimal(
                str(profile.profit_protection_trigger_r)
            )
        ):
            locked_profit_r = Decimal(
                str(profile.locked_profit_r)
            )

            initial_risk_distance = Decimal(
                str(managed_position.initial_risk_distance)
            )

            if direction == "buy":
                target = (
                    entry_price
                    + (
                        locked_profit_r
                        * initial_risk_distance
                    )
                )
            else:
                target = (
                    entry_price
                    - (
                        locked_profit_r
                        * initial_risk_distance
                    )
                )

            candidates.append(
                ("profit-protection", target)
            )

            checks.append(
                "Profit-protection trigger is configured "
                "and reached"
            )

        if (
            profile.trailing_enabled
            and profile.trailing_activation_r is not None
            and profile.trailing_distance_r is not None
            and current_r >= Decimal(
                str(profile.trailing_activation_r)
            )
        ):
            distance_r = Decimal(
                str(profile.trailing_distance_r)
            )

            initial_risk_distance = Decimal(
                str(managed_position.initial_risk_distance)
            )

            trailing_distance = (
                distance_r
                * initial_risk_distance
            )

            if direction == "buy":
                target = current_price - trailing_distance
            else:
                target = current_price + trailing_distance

            candidates.append(
                ("trailing", target)
            )

            checks.append(
                "Trailing trigger is configured and reached"
            )

        if not candidates:
            return (
                self.DECISION_HOLD,
                None,
                None,
            )

        valid_candidates: list[
            tuple[str, Decimal]
        ] = []

        for rule_name, target in candidates:
            if not self._validate_stop_loss_geometry(
                direction,
                current_price,
                target,
            ):
                warnings.append(
                    f"{rule_name} stop-loss proposal rejected "
                    "because it would not remain on the "
                    "correct side of the live market price."
                )
                continue

            if not self._does_stop_reduce_risk(
                direction,
                entry_price,
                initial_stop_loss,
                target,
            ):
                warnings.append(
                    f"{rule_name} stop-loss proposal rejected "
                    "because it would not reduce or preserve "
                    "the original risk distance."
                )
                continue

            if not self._is_stop_loss_improvement(
                direction,
                current_stop_loss,
                target,
            ):
                warnings.append(
                    f"{rule_name} stop-loss proposal rejected "
                    "because it would not improve the current "
                    "broker stop loss."
                )
                continue

            valid_candidates.append(
                (rule_name, target)
            )

        if not valid_candidates:
            return (
                self.DECISION_HOLD,
                None,
                None,
            )

        if direction == "buy":
            rule_name, target = max(
                valid_candidates,
                key=lambda item: item[1],
            )
        else:
            rule_name, target = min(
                valid_candidates,
                key=lambda item: item[1],
            )

        checks.append(
            f"{rule_name} stop-loss proposal passed "
            "risk-increase prevention checks"
        )

        return (
            self.DECISION_MOVE_SL,
            target,
            None,
        )

    def _evaluate_partial_profit(
        self,
        profile: ManagementProfile,
        current_r: Decimal,
        checks: list[str],
        warnings: list[str],
    ) -> tuple[str, Decimal | None]:
        candidates: list[
            tuple[str, Decimal, Decimal]
        ] = []

        if (
            profile.partial_profit_enabled
            and profile.partial_1_trigger_r is not None
            and profile.partial_1_percent is not None
            and current_r >= Decimal(
                str(profile.partial_1_trigger_r)
            )
        ):
            candidates.append(
                (
                    "partial-1",
                    Decimal(
                        str(profile.partial_1_trigger_r)
                    ),
                    Decimal(
                        str(profile.partial_1_percent)
                    ),
                )
            )

        if (
            profile.partial_profit_enabled
            and profile.partial_2_trigger_r is not None
            and profile.partial_2_percent is not None
            and current_r >= Decimal(
                str(profile.partial_2_trigger_r)
            )
        ):
            candidates.append(
                (
                    "partial-2",
                    Decimal(
                        str(profile.partial_2_trigger_r)
                    ),
                    Decimal(
                        str(profile.partial_2_percent)
                    ),
                )
            )

        if not candidates:
            return (
                self.DECISION_HOLD,
                None,
            )

        _, _, percentage = max(
            candidates,
            key=lambda item: item[1],
        )

        if percentage <= 0 or percentage > 100:
            warnings.append(
                "Configured partial-profit percentage is "
                "outside the valid 0-100% range."
            )
            return (
                self.DECISION_HOLD,
                None,
            )

        checks.append(
            "Configured partial-profit trigger is reached"
        )

        warnings.append(
            "Partial-profit evaluation is read-only; "
            "no MT5 position volume has been changed."
        )

        return (
            self.DECISION_PARTIAL_CLOSE,
            percentage,
        )

    def _evaluate_duration(
        self,
        profile: ManagementProfile,
        managed_position: ManagedPosition,
        checks: list[str],
        warnings: list[str],
    ) -> bool:
        if (
            profile.max_management_duration_minutes is None
            or managed_position.opened_at is None
        ):
            return False

        duration_minutes = (
            int(profile.max_management_duration_minutes)
        )

        if duration_minutes <= 0:
            warnings.append(
                "Configured maximum management duration "
                "is not positive and was ignored."
            )
            return False

        opened_at = managed_position.opened_at

        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(
                tzinfo=timezone.utc
            )

        elapsed_seconds = (
            datetime.now(timezone.utc)
            - opened_at
        ).total_seconds()

        if elapsed_seconds >= duration_minutes * 60:
            checks.append(
                "Maximum management duration has been reached"
            )

            warnings.append(
                "Duration-based close is read-only; "
                "no MT5 close order has been sent."
            )

            return True

        return False

    def evaluate(
        self,
        db: Session,
        user_id: int,
        position_ticket: int,
    ) -> AITradeManagementResult:
        if user_id is None:
            raise AITradeManagementError(
                "Authenticated user is required."
            )

        try:
            ticket = int(position_ticket)
        except (TypeError, ValueError) as exc:
            raise AITradeManagementError(
                "Position ticket must be a valid integer."
            ) from exc

        account = self._get_verified_mt5_account(
            db=db,
            user_id=user_id,
        )

        managed_position = (
            db.query(ManagedPosition)
            .filter(
                ManagedPosition.id.is_not(None),
                ManagedPosition.user_id == user_id,
                ManagedPosition.mt5_account_id == account.id,
                ManagedPosition.position_ticket == ticket,
                ManagedPosition.status == "open",
            )
            .first()
        )

        if managed_position is None:
            raise AITradeManagementError(
                "Open reconciled managed position was not found "
                "for this user and MT5 account."
            )

        current_position = (
            self.position_manager.get_position(ticket)
        )

        if current_position is None:
            raise AITradeManagementError(
                "The reconciled position is no longer present "
                "as an open platform-owned MT5 position."
            )

        if int(current_position["ticket"]) != ticket:
            raise AITradeManagementError(
                "Live MT5 position ticket does not match "
                "the managed position."
            )

        if (
            current_position["symbol"].strip().upper()
            != managed_position.broker_symbol.strip().upper()
        ):
            raise AITradeManagementError(
                "Live MT5 broker symbol does not match "
                "the reconciled managed position."
            )

        if (
            current_position["type"].strip().lower()
            != managed_position.direction.strip().lower()
        ):
            raise AITradeManagementError(
                "Live MT5 position direction does not match "
                "the reconciled managed position."
            )

        profile = (
            db.query(ManagementProfile)
            .filter(
                ManagementProfile.managed_position_id
                == managed_position.id,
            )
            .first()
        )

        checks = [
            "Authenticated user verified",
            "MT5 account ownership verified",
            "Managed position belongs to the verified MT5 account",
            "Managed position is open",
            "Live MT5 position refreshed",
            "Live MT5 position ticket verified",
            "Live MT5 broker symbol verified",
            "Live MT5 direction verified",
        ]

        warnings: list[str] = []
        errors: list[str] = []

        if profile is None:
            return self._result(
                managed_position=managed_position,
                profile=None,
                evaluated=True,
                status="profile_missing",
                decision=self.DECISION_HOLD,
                user_id=user_id,
                current_position=current_position,
                checks=checks,
                errors=[
                    "No management profile is attached "
                    "to the managed position."
                ],
                message=(
                    "Management evaluation stopped safely "
                    "because no management profile exists."
                ),
            )

        checks.append(
            "Management profile loaded from the managed position"
        )

        if not profile.ai_management_enabled:
            checks.append(
                "AI management is disabled for this position"
            )

            return self._result(
                managed_position=managed_position,
                profile=profile,
                evaluated=True,
                status="disabled",
                decision=self.DECISION_HOLD,
                user_id=user_id,
                current_position=current_position,
                checks=checks,
                warnings=warnings,
                message=(
                    "AI management is disabled for this "
                    "position. No management action is proposed."
                ),
            )

        checks.append(
            "AI management is enabled for this position"
        )

        if managed_position.initial_risk_distance is None:
            return self._result(
                managed_position=managed_position,
                profile=profile,
                evaluated=True,
                status="risk_context_missing",
                decision=self.DECISION_HOLD,
                user_id=user_id,
                current_position=current_position,
                checks=checks,
                errors=[
                    "Initial risk distance is missing."
                ],
                message=(
                    "Management evaluation stopped safely "
                    "because the initial risk context is incomplete."
                ),
            )

        entry_price = Decimal(
            str(current_position["entry_price"])
        )

        current_price = Decimal(
            str(current_position["current_price"])
        )

        initial_risk_distance = Decimal(
            str(managed_position.initial_risk_distance)
        )

        if initial_risk_distance <= 0:
            return self._result(
                managed_position=managed_position,
                profile=profile,
                evaluated=True,
                status="risk_context_invalid",
                decision=self.DECISION_HOLD,
                user_id=user_id,
                current_position=current_position,
                checks=checks,
                errors=[
                    "Initial risk distance must be greater than zero."
                ],
                message=(
                    "Management evaluation stopped safely "
                    "because the initial risk distance is invalid."
                ),
            )

        current_r = self._calculate_current_r(
            direction=managed_position.direction,
            entry_price=entry_price,
            current_price=current_price,
            initial_risk_distance=initial_risk_distance,
        )

        checks.append(
            "Current R-multiple calculated from reconciled "
            "initial risk distance"
        )

        has_active_rule = any(
            [
                bool(
                    profile.break_even_enabled
                    and profile.break_even_trigger_r is not None
                    and profile.break_even_offset is not None
                ),
                bool(
                    profile.partial_profit_enabled
                    and (
                        profile.partial_1_trigger_r is not None
                        or profile.partial_2_trigger_r is not None
                    )
                ),
                bool(
                    profile.profit_protection_enabled
                    and profile.profit_protection_trigger_r is not None
                    and profile.locked_profit_r is not None
                ),
                bool(
                    profile.trailing_enabled
                    and profile.trailing_activation_r is not None
                    and profile.trailing_distance_r is not None
                ),
                bool(
                    profile.max_management_duration_minutes
                    is not None
                ),
            ]
        )

        if not has_active_rule:
            checks.append(
                "No management rule is currently configured"
            )

            return self._result(
                managed_position=managed_position,
                profile=profile,
                evaluated=True,
                status="no_rules_configured",
                decision=self.DECISION_HOLD,
                user_id=user_id,
                current_position=current_position,
                current_r=current_r,
                checks=checks,
                warnings=warnings,
                message=(
                    "AI management is enabled, but no management "
                    "rules are configured for this position."
                ),
            )

        if self._evaluate_duration(
            profile=profile,
            managed_position=managed_position,
            checks=checks,
            warnings=warnings,
        ):
            return self._result(
                managed_position=managed_position,
                profile=profile,
                evaluated=True,
                status="decision_ready",
                decision=self.DECISION_CLOSE_POSITION,
                user_id=user_id,
                current_position=current_position,
                current_r=current_r,
                checks=checks,
                warnings=warnings,
                message=(
                    "The configured maximum management duration "
                    "has been reached. A close decision is proposed; "
                    "no MT5 action has been sent."
                ),
            )

        stop_decision, proposed_stop_loss, _ = (
            self._evaluate_stop_rules(
                managed_position=managed_position,
                profile=profile,
                current_position=current_position,
                current_r=current_r,
                checks=checks,
                warnings=warnings,
            )
        )

        if stop_decision == self.DECISION_MOVE_SL:
            return self._result(
                managed_position=managed_position,
                profile=profile,
                evaluated=True,
                status="decision_ready",
                decision=stop_decision,
                user_id=user_id,
                current_position=current_position,
                current_r=current_r,
                proposed_stop_loss=proposed_stop_loss,
                checks=checks,
                warnings=warnings,
                message=(
                    "A configured stop-loss management rule "
                    "has produced a risk-reducing proposal. "
                    "No MT5 modification has been sent."
                ),
            )

        partial_decision, partial_percentage = (
            self._evaluate_partial_profit(
                profile=profile,
                current_r=current_r,
                checks=checks,
                warnings=warnings,
            )
        )

        if partial_decision == self.DECISION_PARTIAL_CLOSE:
            return self._result(
                managed_position=managed_position,
                profile=profile,
                evaluated=True,
                status="decision_ready",
                decision=partial_decision,
                user_id=user_id,
                current_position=current_position,
                current_r=current_r,
                partial_close_percent=partial_percentage,
                checks=checks,
                warnings=warnings,
                message=(
                    "A configured partial-profit rule has "
                    "produced a close-volume proposal. "
                    "No MT5 volume change has been sent."
                ),
            )

        checks.append(
            "No configured management rule currently requires action"
        )

        return self._result(
            managed_position=managed_position,
            profile=profile,
            evaluated=True,
            status="evaluated",
            decision=self.DECISION_HOLD,
            user_id=user_id,
            current_position=current_position,
            current_r=current_r,
            checks=checks,
            warnings=warnings,
            errors=errors,
            message=(
                "Position evaluated successfully. "
                "No management action is currently required."
            ),
        )


ai_trade_management_service = AITradeManagementService()
