from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.execution.position_manager import PositionManager
from app.models.ai_management_action import AIManagementAction
from app.models.management_profile import ManagementProfile
from app.models.managed_position import ManagedPosition
from app.models.mt5_trading_account import MT5TradingAccount
from app.services.ai_trade_management_service import (
    AITradeManagementService,
)
from app.services.ai_trade_management_execution_service import (
    AITradeManagementExecutionError,
    AITradeManagementExecutionService,
)


class AITradeManagementOrchestrationError(Exception):
    """Raised when controlled AI management execution cannot continue."""


class AITradeManagementOrchestrationService:
    """
    Controlled C.2 execution pipeline.

    Evaluates the live position first, creates a deterministic action
    record, sends only the evaluator-approved decision, then reconciles
    the actual MT5 position back into ManagedPosition.
    """

    def __init__(self) -> None:
        self.evaluator = AITradeManagementService()
        self.executor = AITradeManagementExecutionService()
        self.position_manager = PositionManager()

    def _get_account(
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
            raise AITradeManagementOrchestrationError(
                "No active MT5 trading account is registered for this user."
            )

        return account

    def _get_managed_position(
        self,
        db: Session,
        user_id: int,
        account_id: int,
        position_ticket: int,
    ) -> ManagedPosition:
        position = (
            db.query(ManagedPosition)
            .filter(
                ManagedPosition.user_id == user_id,
                ManagedPosition.mt5_account_id == account_id,
                ManagedPosition.position_ticket == position_ticket,
                ManagedPosition.status == "open",
            )
            .first()
        )

        if position is None:
            raise AITradeManagementOrchestrationError(
                "Open reconciled managed position was not found."
            )

        return position

    def _get_profile(
        self,
        db: Session,
        managed_position_id: int,
    ) -> ManagementProfile:
        profile = (
            db.query(ManagementProfile)
            .filter(
                ManagementProfile.managed_position_id
                == managed_position_id,
            )
            .first()
        )

        if profile is None:
            raise AITradeManagementOrchestrationError(
                "Management profile was not found."
            )

        return profile

    def _partial_action_key(
        self,
        position_ticket: int,
        percent: Decimal,
    ) -> str:
        return (
            f"{position_ticket}:PARTIAL_CLOSE:"
            f"{percent.normalize()}"
        )

    def _action_key(
        self,
        position_ticket: int,
        decision: str,
        proposed_stop_loss: Decimal | None,
        partial_percent: Decimal | None,
    ) -> str:
        if decision == "MOVE_SL":
            return (
                f"{position_ticket}:MOVE_SL:"
                f"{proposed_stop_loss.normalize()}"
            )

        if decision == "PARTIAL_CLOSE":
            if partial_percent is None:
                raise AITradeManagementOrchestrationError(
                    "Partial-close decision has no percentage."
                )

            return self._partial_action_key(
                position_ticket,
                partial_percent,
            )

        if decision == "CLOSE_POSITION":
            return f"{position_ticket}:CLOSE_POSITION"

        return f"{position_ticket}:{decision}"

    def _find_existing_action(
        self,
        db: Session,
        action_key: str,
    ) -> AIManagementAction | None:
        return (
            db.query(AIManagementAction)
            .filter(
                AIManagementAction.action_key == action_key,
            )
            .first()
        )

    def _reconcile_position(
        self,
        db: Session,
        managed_position: ManagedPosition,
    ) -> dict:
        live_position = self.position_manager.get_position(
            managed_position.position_ticket
        )

        now = datetime.now(timezone.utc)

        if live_position is None:
            managed_position.status = "closed"
            managed_position.volume = Decimal("0")
            managed_position.current_price = None
            managed_position.profit_loss = Decimal("0")
            managed_position.last_reconciled_at = now
            managed_position.closed_at = now

            return {
                "exists": False,
                "position": None,
            }

        managed_position.volume = Decimal(
            str(live_position["volume"])
        )

        managed_position.current_price = Decimal(
            str(live_position["current_price"])
        )

        managed_position.stop_loss = (
            Decimal(str(live_position["stop_loss"]))
            if live_position.get("stop_loss") is not None
            else None
        )

        managed_position.take_profit = (
            Decimal(str(live_position["take_profit"]))
            if live_position.get("take_profit") is not None
            else None
        )

        managed_position.profit_loss = Decimal(
            str(live_position["profit"])
        )

        managed_position.last_reconciled_at = now

        return {
            "exists": True,
            "position": live_position,
        }

    def execute(
        self,
        db: Session,
        user_id: int,
        position_ticket: int,
    ) -> dict:
        account = self._get_account(
            db,
            user_id,
        )

        managed_position = self._get_managed_position(
            db,
            user_id,
            account.id,
            position_ticket,
        )

        profile = self._get_profile(
            db,
            managed_position.id,
        )

        evaluation = self.evaluator.evaluate(
            db=db,
            user_id=user_id,
            position_ticket=position_ticket,
        )

        decision = evaluation.decision

        if decision == "HOLD":
            return {
                "executed": False,
                "status": "hold",
                "decision": decision,
                "evaluation": evaluation.serialize(),
                "message": "AI management evaluated the position and produced HOLD.",
            }

        if decision not in {
            "MOVE_SL",
            "PARTIAL_CLOSE",
            "CLOSE_POSITION",
        }:
            raise AITradeManagementOrchestrationError(
                f"Unsupported AI management decision: {decision}"
            )

        proposed_stop_loss = evaluation.proposed_stop_loss
        partial_percent = evaluation.partial_close_percent

        action_key = self._action_key(
            position_ticket=position_ticket,
            decision=decision,
            proposed_stop_loss=proposed_stop_loss,
            partial_percent=partial_percent,
        )

        existing = self._find_existing_action(
            db,
            action_key,
        )

        if existing is not None:
            if existing.status in {
                "reconciled",
                "already_applied",
            }:
                return {
                    "executed": False,
                    "status": "duplicate_blocked",
                    "decision": decision,
                    "action_key": action_key,
                    "message": (
                        "The same AI management action has already "
                        "been reconciled."
                    ),
                }

            if existing.status == "sent_reconciliation_required":
                reconciliation = self._reconcile_position(
                    db,
                    managed_position,
                )

                if decision == "MOVE_SL":
                    target = proposed_stop_loss

                    if (
                        reconciliation["exists"]
                        and target is not None
                        and reconciliation["position"] is not None
                    ):
                        live_sl = reconciliation["position"]["stop_loss"]

                        if (
                            live_sl is not None
                            and Decimal(str(live_sl)) == target
                        ):
                            existing.status = "reconciled"
                            existing.message = (
                                "Previously sent stop-loss action "
                                "confirmed by live broker state."
                            )
                            db.commit()

                            return {
                                "executed": False,
                                "status": "already_applied",
                                "decision": decision,
                                "action_key": action_key,
                                "message": existing.message,
                            }

                if decision == "CLOSE_POSITION" and not reconciliation["exists"]:
                    existing.status = "reconciled"
                    existing.message = (
                        "Previously sent close action confirmed by "
                        "absence of the live position."
                    )
                    db.commit()

                    return {
                        "executed": False,
                        "status": "already_applied",
                        "decision": decision,
                        "action_key": action_key,
                        "message": existing.message,
                    }

                db.commit()

                raise AITradeManagementOrchestrationError(
                    "A previous management action was sent to MT5 but "
                    "could not yet be confirmed from the live position."
                )

        action = AIManagementAction(
            user_id=user_id,
            mt5_account_id=account.id,
            managed_position_id=managed_position.id,
            position_ticket=position_ticket,
            decision=decision,
            action_key=action_key,
            status="created",
            requested_stop_loss=proposed_stop_loss,
            partial_close_percent=partial_percent,
        )

        db.add(action)

        try:
            db.flush()

            if decision == "MOVE_SL":
                if proposed_stop_loss is None:
                    raise AITradeManagementOrchestrationError(
                        "MOVE_SL decision has no proposed stop loss."
                    )

                result = self.executor.move_stop_loss(
                    db=db,
                    user_id=user_id,
                    position_ticket=position_ticket,
                    proposed_stop_loss=proposed_stop_loss,
                )

            elif decision == "PARTIAL_CLOSE":
                if partial_percent is None:
                    raise AITradeManagementOrchestrationError(
                        "PARTIAL_CLOSE decision has no percentage."
                    )

                live_position = self.position_manager.get_position(
                    position_ticket
                )

                if live_position is None:
                    raise AITradeManagementOrchestrationError(
                        "Live position disappeared before partial-close execution."
                    )

                live_volume = Decimal(
                    str(live_position["volume"])
                )

                close_volume = (
                    live_volume
                    * partial_percent
                    / Decimal("100")
                )

                result = self.executor.close_position(
                    db=db,
                    user_id=user_id,
                    position_ticket=position_ticket,
                    decision="PARTIAL_CLOSE",
                    close_volume=close_volume,
                )

            else:
                result = self.executor.close_position(
                    db=db,
                    user_id=user_id,
                    position_ticket=position_ticket,
                    decision="CLOSE_POSITION",
                )

            action.status = "sent_reconciliation_required"
            action.retcode = result.retcode
            action.retcode_description = result.retcode_description
            action.message = result.message

            db.flush()

        except (
            AITradeManagementExecutionError,
            AITradeManagementOrchestrationError,
        ) as exc:
            action.status = "failed"
            action.message = str(exc)
            db.commit()
            raise

        reconciliation = self._reconcile_position(
            db,
            managed_position,
        )

        if decision == "PARTIAL_CLOSE":
            if partial_percent is not None:
                if (
                    profile.partial_2_percent is not None
                    and partial_percent
                    == Decimal(str(profile.partial_2_percent))
                ):
                    profile_partial_2_trigger = profile.partial_2_trigger_r
                    if profile_partial_2_trigger is not None:
                        profile_partial_2_trigger = Decimal(
                            str(profile_partial_2_trigger)
                        )

                    if (
                        evaluation.current_r is not None
                        and profile_partial_2_trigger is not None
                        and evaluation.current_r
                        >= profile_partial_2_trigger
                    ):
                        action.message = (
                            action.message
                            or ""
                        ) + " Partial-2 management action reconciled."

                if (
                    profile.partial_1_percent is not None
                    and partial_percent
                    == Decimal(str(profile.partial_1_percent))
                ):
                    profile_partial_1_trigger = profile.partial_1_trigger_r
                    if profile_partial_1_trigger is not None:
                        profile_partial_1_trigger = Decimal(
                            str(profile_partial_1_trigger)
                        )

                    if (
                        evaluation.current_r is not None
                        and profile_partial_1_trigger is not None
                        and evaluation.current_r
                        >= profile_partial_1_trigger
                    ):
                        action.message = (
                            action.message
                            or ""
                        ) + " Partial-1 management action reconciled."

        if decision == "MOVE_SL":
            action.status = "reconciled" if reconciliation["exists"] else "sent_reconciliation_required"

        elif decision == "PARTIAL_CLOSE":
            action.status = "reconciled" if reconciliation["exists"] else "sent_reconciliation_required"

        elif decision == "CLOSE_POSITION":
            action.status = (
                "reconciled"
                if not reconciliation["exists"]
                else "sent_reconciliation_required"
            )

        db.commit()

        return {
            "executed": result.executed,
            "status": action.status,
            "decision": decision,
            "action_key": action_key,
            "execution": result.serialize(),
            "evaluation": evaluation.serialize(),
            "reconciliation": reconciliation,
            "message": action.message,
        }


ai_trade_management_orchestration_service = (
    AITradeManagementOrchestrationService()
)
