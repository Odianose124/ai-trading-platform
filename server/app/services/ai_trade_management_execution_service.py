from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import MetaTrader5 as mt5
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


class AITradeManagementExecutionError(Exception):
    """Raised when a management action cannot be safely executed."""


@dataclass
class AITradeManagementExecutionResult:
    executed: bool
    status: str
    decision: str
    user_id: int | None
    managed_position_id: int | None
    position_ticket: int | None
    broker_symbol: str | None
    direction: str | None
    requested_volume: Decimal | None
    executed_volume: Decimal | None
    requested_stop_loss: Decimal | None
    executed_stop_loss: Decimal | None
    requested_take_profit: Decimal | None
    executed_take_profit: Decimal | None
    broker_price: Decimal | None
    retcode: int | None
    retcode_description: str | None
    checks: list[str]
    warnings: list[str]
    errors: list[str]
    message: str

    def serialize(self) -> dict[str, Any]:
        return {
            "executed": self.executed,
            "status": self.status,
            "decision": self.decision,
            "user_id": self.user_id,
            "managed_position_id": self.managed_position_id,
            "position_ticket": self.position_ticket,
            "broker_symbol": self.broker_symbol,
            "direction": self.direction,
            "requested_volume": (
                float(self.requested_volume)
                if self.requested_volume is not None
                else None
            ),
            "executed_volume": (
                float(self.executed_volume)
                if self.executed_volume is not None
                else None
            ),
            "requested_stop_loss": (
                float(self.requested_stop_loss)
                if self.requested_stop_loss is not None
                else None
            ),
            "executed_stop_loss": (
                float(self.executed_stop_loss)
                if self.executed_stop_loss is not None
                else None
            ),
            "requested_take_profit": (
                float(self.requested_take_profit)
                if self.requested_take_profit is not None
                else None
            ),
            "executed_take_profit": (
                float(self.executed_take_profit)
                if self.executed_take_profit is not None
                else None
            ),
            "broker_price": (
                float(self.broker_price)
                if self.broker_price is not None
                else None
            ),
            "retcode": self.retcode,
            "retcode_description": self.retcode_description,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "message": self.message,
        }


class AITradeManagementExecutionService:
    """
    Dedicated execution boundary for AI trade-management actions.

    Supported decisions:
        MOVE_SL
        PARTIAL_CLOSE
        CLOSE_POSITION

    HOLD is never sent to MT5.

    This service is deliberately separate from the opening-order
    execution service. It may modify an already-reconciled position,
    but it must never open a new position.

    Every live action requires:
        authenticated user
        verified MT5 ownership
        reconciled managed position
        live broker position
        ticket/symbol/direction verification
        management profile verification
        fresh broker symbol metadata
        broker preflight validation
        explicit MT5 action
    """

    DECISION_HOLD = "HOLD"
    DECISION_MOVE_SL = "MOVE_SL"
    DECISION_PARTIAL_CLOSE = "PARTIAL_CLOSE"
    DECISION_CLOSE_POSITION = "CLOSE_POSITION"

    MAGIC_NUMBER = 202609

    def __init__(self) -> None:
        self.position_manager = PositionManager()

    @staticmethod
    def _decimal(
        value: Any,
        field_name: str,
    ) -> Decimal:
        try:
            result = Decimal(str(value))

            if not result.is_finite():
                raise InvalidOperation

            return result

        except (InvalidOperation, ValueError, TypeError) as exc:
            raise AITradeManagementExecutionError(
                f"{field_name} is not a valid finite number."
            ) from exc

    @staticmethod
    def _normalize_direction(direction: Any) -> str:
        normalized = str(direction or "").strip().lower()

        if normalized in {"buy", "long"}:
            return "buy"

        if normalized in {"sell", "short"}:
            return "sell"

        return normalized

    @staticmethod
    def _retcode_description(retcode: int) -> str:
        descriptions = {
            getattr(mt5, "TRADE_RETCODE_DONE", -1): "Request completed",
            getattr(mt5, "TRADE_RETCODE_PLACED", -1): "Order placed",
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", -1): (
                "Request completed partially"
            ),
            getattr(mt5, "TRADE_RETCODE_REQUOTE", -1): "Requote",
            getattr(mt5, "TRADE_RETCODE_REJECT", -1): "Request rejected",
            getattr(mt5, "TRADE_RETCODE_CANCEL", -1): "Request cancelled",
            getattr(mt5, "TRADE_RETCODE_ERROR", -1): "Request error",
            getattr(mt5, "TRADE_RETCODE_TIMEOUT", -1): "Request timeout",
            getattr(mt5, "TRADE_RETCODE_INVALID", -1): "Invalid request",
            getattr(mt5, "TRADE_RETCODE_INVALID_VOLUME", -1): (
                "Invalid volume"
            ),
            getattr(mt5, "TRADE_RETCODE_INVALID_PRICE", -1): (
                "Invalid price"
            ),
            getattr(mt5, "TRADE_RETCODE_INVALID_STOPS", -1): (
                "Invalid stops"
            ),
            getattr(mt5, "TRADE_RETCODE_TRADE_DISABLED", -1): (
                "Trading disabled"
            ),
            getattr(mt5, "TRADE_RETCODE_MARKET_CLOSED", -1): (
                "Market closed"
            ),
            getattr(mt5, "TRADE_RETCODE_NO_MONEY", -1): "Insufficient funds",
            getattr(mt5, "TRADE_RETCODE_PRICE_CHANGED", -1): (
                "Price changed"
            ),
            getattr(mt5, "TRADE_RETCODE_PRICE_OFF", -1): (
                "No quotes"
            ),
        }

        return descriptions.get(
            retcode,
            f"MT5 retcode {retcode}",
        )

    @staticmethod
    def _round_price(
        price: Decimal,
        digits: int,
    ) -> float:
        quantum = Decimal("1").scaleb(-digits)

        return float(
            price.quantize(
                quantum
            )
        )

    @staticmethod
    def _normalize_volume(
        volume: Decimal,
        volume_min: Decimal,
        volume_max: Decimal,
        volume_step: Decimal,
    ) -> Decimal:
        if volume <= 0:
            raise AITradeManagementExecutionError(
                "Management execution volume must be greater than zero."
            )

        if volume_min <= 0 or volume_max <= 0 or volume_step <= 0:
            raise AITradeManagementExecutionError(
                "Broker returned invalid volume constraints."
            )

        if volume < volume_min:
            raise AITradeManagementExecutionError(
                "Requested management volume is below the broker minimum."
            )

        if volume > volume_max:
            raise AITradeManagementExecutionError(
                "Requested management volume exceeds the broker maximum."
            )

        steps = (
            volume / volume_step
        ).to_integral_value()

        normalized = steps * volume_step

        if normalized < volume_min:
            normalized = volume_min

        if normalized > volume_max:
            normalized = volume_max

        return normalized

    def _get_verified_account(
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
            raise AITradeManagementExecutionError(
                "No active MT5 trading account is registered for this user."
            )

        try:
            mt5_connection.ensure_connected()

            mt5_connection.verify_account(
                expected_login=account.mt5_login,
                expected_server=account.server,
            )

        except MT5AccountMismatchError as exc:
            raise AITradeManagementExecutionError(
                str(exc)
            ) from exc

        except MT5ConnectionError as exc:
            raise AITradeManagementExecutionError(
                str(exc)
            ) from exc

        return account

    def _load_verified_position(
        self,
        db: Session,
        user_id: int,
        account: MT5TradingAccount,
        position_ticket: int,
    ) -> tuple[ManagedPosition, ManagementProfile, dict]:
        managed_position = (
            db.query(ManagedPosition)
            .filter(
                ManagedPosition.user_id == user_id,
                ManagedPosition.mt5_account_id == account.id,
                ManagedPosition.position_ticket == position_ticket,
                ManagedPosition.status == "open",
            )
            .first()
        )

        if managed_position is None:
            raise AITradeManagementExecutionError(
                "Open reconciled managed position was not found "
                "for this user and MT5 account."
            )

        profile = (
            db.query(ManagementProfile)
            .filter(
                ManagementProfile.managed_position_id
                == managed_position.id,
            )
            .first()
        )

        if profile is None:
            raise AITradeManagementExecutionError(
                "No management profile is attached to the managed position."
            )

        if not profile.ai_management_enabled:
            raise AITradeManagementExecutionError(
                "AI management is disabled for this position."
            )

        live_position = (
            self.position_manager.get_position(
                position_ticket
            )
        )

        if live_position is None:
            raise AITradeManagementExecutionError(
                "The managed position is no longer present "
                "as an open platform-owned MT5 position."
            )

        if int(live_position["ticket"]) != position_ticket:
            raise AITradeManagementExecutionError(
                "Live MT5 position ticket does not match the managed position."
            )

        managed_symbol = (
            managed_position.broker_symbol.strip().upper()
        )

        live_symbol = (
            str(live_position["symbol"]).strip().upper()
        )

        if managed_symbol != live_symbol:
            raise AITradeManagementExecutionError(
                "Live MT5 broker symbol does not match the managed position."
            )

        managed_direction = self._normalize_direction(
            managed_position.direction
        )

        live_direction = self._normalize_direction(
            live_position["type"]
        )

        if managed_direction != live_direction:
            raise AITradeManagementExecutionError(
                "Live MT5 position direction does not match "
                "the managed position."
            )

        return (
            managed_position,
            profile,
            live_position,
        )

    def _get_symbol_info(
        self,
        broker_symbol: str,
    ):
        info = mt5.symbol_info(
            broker_symbol
        )

        if info is None:
            raise AITradeManagementExecutionError(
                "MT5 symbol information could not be loaded for "
                f"{broker_symbol}."
            )

        if not getattr(info, "visible", True):
            if not mt5.symbol_select(
                broker_symbol,
                True,
            ):
                raise AITradeManagementExecutionError(
                    "MT5 broker symbol is not visible and could not "
                    "be selected."
                )

            info = mt5.symbol_info(
                broker_symbol
            )

            if info is None:
                raise AITradeManagementExecutionError(
                    "MT5 symbol information became unavailable "
                    "after symbol selection."
                )

        return info

    def _validate_stop_loss_proposal(
        self,
        managed_position: ManagedPosition,
        live_position: dict,
        proposed_stop_loss: Decimal,
        info,
    ) -> Decimal:
        direction = self._normalize_direction(
            managed_position.direction
        )

        current_price = self._decimal(
            live_position["current_price"],
            "current_price",
        )

        entry_price = self._decimal(
            live_position["entry_price"],
            "entry_price",
        )

        initial_stop_loss = (
            self._decimal(
                managed_position.initial_stop_loss,
                "initial_stop_loss",
            )
            if managed_position.initial_stop_loss is not None
            else None
        )

        current_stop_loss = (
            self._decimal(
                live_position["stop_loss"],
                "stop_loss",
            )
            if live_position.get("stop_loss") is not None
            else None
        )

        digits = int(
            getattr(info, "digits", 0) or 0
        )

        if direction == "buy":
            if proposed_stop_loss >= current_price:
                raise AITradeManagementExecutionError(
                    "Proposed BUY stop loss must remain below "
                    "the live market price."
                )

            if current_stop_loss is not None and (
                proposed_stop_loss <= current_stop_loss
            ):
                raise AITradeManagementExecutionError(
                    "Proposed BUY stop loss does not improve "
                    "the current broker stop loss."
                )

            if initial_stop_loss is None:
                raise AITradeManagementExecutionError(
                    "Initial stop loss is missing; management execution "
                    "cannot safely increase risk."
                )

            if (
                entry_price - proposed_stop_loss
                > entry_price - initial_stop_loss
            ):
                raise AITradeManagementExecutionError(
                    "Proposed BUY stop loss would increase "
                    "the original risk distance."
                )

        elif direction == "sell":
            if proposed_stop_loss <= current_price:
                raise AITradeManagementExecutionError(
                    "Proposed SELL stop loss must remain above "
                    "the live market price."
                )

            if current_stop_loss is not None and (
                proposed_stop_loss >= current_stop_loss
            ):
                raise AITradeManagementExecutionError(
                    "Proposed SELL stop loss does not improve "
                    "the current broker stop loss."
                )

            if initial_stop_loss is None:
                raise AITradeManagementExecutionError(
                    "Initial stop loss is missing; management execution "
                    "cannot safely increase risk."
                )

            if (
                proposed_stop_loss - entry_price
                > initial_stop_loss - entry_price
            ):
                raise AITradeManagementExecutionError(
                    "Proposed SELL stop loss would increase "
                    "the original risk distance."
                )

        else:
            raise AITradeManagementExecutionError(
                "Managed position direction is invalid."
            )

        trade_stops_level = int(
            getattr(info, "trade_stops_level", 0) or 0
        )

        point = self._decimal(
            getattr(info, "point", 0),
            "broker_point",
        )

        if trade_stops_level > 0 and point > 0:
            minimum_distance = (
                Decimal(trade_stops_level)
                * point
            )

            if direction == "buy":
                if (
                    current_price - proposed_stop_loss
                    < minimum_distance
                ):
                    raise AITradeManagementExecutionError(
                        "Proposed BUY stop loss is inside "
                        "the broker minimum stop distance."
                    )

            else:
                if (
                    proposed_stop_loss - current_price
                    < minimum_distance
                ):
                    raise AITradeManagementExecutionError(
                        "Proposed SELL stop loss is inside "
                        "the broker minimum stop distance."
                    )

        return proposed_stop_loss.quantize(
            Decimal("1").scaleb(-digits)
        )

    def _build_sltp_request(
        self,
        live_position: dict,
        proposed_stop_loss: Decimal,
        info,
    ) -> dict:
        digits = int(
            getattr(info, "digits", 0) or 0
        )

        take_profit = (
            self._decimal(
                live_position["take_profit"],
                "take_profit",
            )
            if live_position.get("take_profit") is not None
            else Decimal("0")
        )

        return {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": int(
                live_position["ticket"]
            ),
            "symbol": str(
                live_position["symbol"]
            ),
            "sl": self._round_price(
                proposed_stop_loss,
                digits,
            ),
            "tp": self._round_price(
                take_profit,
                digits,
            ),
        }

    def _get_filling_mode(
        self,
        info,
    ) -> int:
        filling_mode = getattr(
            info,
            "filling_mode",
            None,
        )

        if filling_mode is not None:
            try:
                return int(filling_mode)
            except (TypeError, ValueError):
                pass

        return mt5.ORDER_FILLING_RETURN

    def _build_close_request(
        self,
        live_position: dict,
        close_volume: Decimal,
        info,
    ) -> tuple[dict, Decimal]:
        direction = self._normalize_direction(
            live_position["type"]
        )

        if direction not in {"buy", "sell"}:
            raise AITradeManagementExecutionError(
                "Live position direction is invalid."
            )

        volume_min = self._decimal(
            getattr(info, "volume_min", 0),
            "volume_min",
        )

        volume_max = self._decimal(
            getattr(info, "volume_max", 0),
            "volume_max",
        )

        volume_step = self._decimal(
            getattr(info, "volume_step", 0),
            "volume_step",
        )

        live_volume = self._decimal(
            live_position["volume"],
            "live_volume",
        )

        if close_volume > live_volume:
            raise AITradeManagementExecutionError(
                "Requested close volume exceeds the live position volume."
            )

        normalized_volume = self._normalize_volume(
            close_volume,
            volume_min,
            volume_max,
            volume_step,
        )

        if normalized_volume > live_volume:
            normalized_volume = live_volume

        tick = mt5.symbol_info_tick(
            str(live_position["symbol"])
        )

        if tick is None:
            raise AITradeManagementExecutionError(
                "Live MT5 tick is unavailable for the management action."
            )

        if direction == "buy":
            close_type = mt5.ORDER_TYPE_SELL
            price = self._decimal(
                tick.bid,
                "close_bid",
            )
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price = self._decimal(
                tick.ask,
                "close_ask",
            )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": str(
                live_position["symbol"]
            ),
            "volume": float(
                normalized_volume
            ),
            "type": close_type,
            "position": int(
                live_position["ticket"]
            ),
            "price": float(price),
            "deviation": 20,
            "magic": self.MAGIC_NUMBER,
            "comment": "AI trade management",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling_mode(info),
        }

        return request, normalized_volume

    def _successful_retcode(
        self,
        retcode: int,
    ) -> bool:
        return retcode in {
            int(
                getattr(
                    mt5,
                    "TRADE_RETCODE_DONE",
                    -1,
                )
            ),
            int(
                getattr(
                    mt5,
                    "TRADE_RETCODE_PLACED",
                    -1,
                )
            ),
            int(
                getattr(
                    mt5,
                    "TRADE_RETCODE_DONE_PARTIAL",
                    -1,
                )
            ),
        }

    def _execute_request(
        self,
        request: dict,
        checks: list[str],
        warnings: list[str],
    ) -> tuple[Any, int, str]:
        preflight = mt5.order_check(
            request
        )

        if preflight is None:
            error_code, error_message = (
                mt5.last_error()
            )

            raise AITradeManagementExecutionError(
                "MT5 management preflight returned no result: "
                f"{error_code} - {error_message}"
            )

        preflight_retcode = int(
            getattr(
                preflight,
                "retcode",
                0,
            )
            or 0
        )

        preflight_comment = str(
            getattr(
                preflight,
                "comment",
                "",
            )
            or ""
        )

        if preflight_retcode != 0:
            raise AITradeManagementExecutionError(
                "MT5 management preflight failed: "
                f"retcode={preflight_retcode}, "
                f"comment={preflight_comment}"
            )

        checks.append(
            "MT5 management order_check passed"
        )

        result = mt5.order_send(
            request
        )

        if result is None:
            error_code, error_message = (
                mt5.last_error()
            )

            raise AITradeManagementExecutionError(
                "MT5 management order_send returned no result: "
                f"{error_code} - {error_message}"
            )

        retcode = int(
            getattr(
                result,
                "retcode",
                0,
            )
            or 0
        )

        description = self._retcode_description(
            retcode
        )

        if not self._successful_retcode(
            retcode
        ):
            raise AITradeManagementExecutionError(
                "MT5 management order was rejected: "
                f"retcode={retcode}, "
                f"description={description}, "
                f"comment={getattr(result, 'comment', '')}"
            )

        warnings.append(
            "MT5 management action was sent successfully; "
            "live-position reconciliation is required."
        )

        return (
            result,
            retcode,
            description,
        )

    def move_stop_loss(
        self,
        db: Session,
        user_id: int,
        position_ticket: int,
        proposed_stop_loss: Decimal,
    ) -> AITradeManagementExecutionResult:
        checks: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []

        account = self._get_verified_account(
            db=db,
            user_id=user_id,
        )

        checks.append(
            "MT5 account ownership verified"
        )

        managed_position, profile, live_position = (
            self._load_verified_position(
                db=db,
                user_id=user_id,
                account=account,
                position_ticket=position_ticket,
            )
        )

        checks.extend(
            [
                "Open reconciled managed position verified",
                "Management profile verified",
                "Live MT5 position refreshed",
                "Live MT5 ticket verified",
                "Live MT5 broker symbol verified",
                "Live MT5 direction verified",
            ]
        )

        if not profile.ai_management_enabled:
            raise AITradeManagementExecutionError(
                "AI management is disabled for this position."
            )

        info = self._get_symbol_info(
            managed_position.broker_symbol
        )

        checks.append(
            "Fresh MT5 broker symbol metadata loaded"
        )

        proposed_stop_loss = self._decimal(
            proposed_stop_loss,
            "proposed_stop_loss",
        )

        validated_stop_loss = (
            self._validate_stop_loss_proposal(
                managed_position=managed_position,
                live_position=live_position,
                proposed_stop_loss=proposed_stop_loss,
                info=info,
            )
        )

        checks.append(
            "Stop-loss proposal passed management risk gates"
        )

        request = self._build_sltp_request(
            live_position=live_position,
            proposed_stop_loss=validated_stop_loss,
            info=info,
        )

        checks.append(
            "MT5 SL/TP modification request built "
            "without opening a new position"
        )

        result, retcode, description = (
            self._execute_request(
                request=request,
                checks=checks,
                warnings=warnings,
            )
        )

        return AITradeManagementExecutionResult(
            executed=True,
            status="execution_reconciliation_required",
            decision=self.DECISION_MOVE_SL,
            user_id=user_id,
            managed_position_id=managed_position.id,
            position_ticket=position_ticket,
            broker_symbol=managed_position.broker_symbol,
            direction=managed_position.direction,
            requested_volume=None,
            executed_volume=None,
            requested_stop_loss=proposed_stop_loss,
            executed_stop_loss=validated_stop_loss,
            requested_take_profit=None,
            executed_take_profit=None,
            broker_price=None,
            retcode=retcode,
            retcode_description=description,
            checks=checks,
            warnings=warnings,
            errors=errors,
            message=(
                "AI stop-loss modification was accepted by MT5. "
                "The live position must be reconciled before the "
                "management action is considered complete."
            ),
        )

    def close_position(
        self,
        db: Session,
        user_id: int,
        position_ticket: int,
        close_volume: Decimal | None = None,
        decision: str = DECISION_CLOSE_POSITION,
    ) -> AITradeManagementExecutionResult:
        checks: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []

        if decision not in {
            self.DECISION_PARTIAL_CLOSE,
            self.DECISION_CLOSE_POSITION,
        }:
            raise AITradeManagementExecutionError(
                "Close execution requires PARTIAL_CLOSE "
                "or CLOSE_POSITION."
            )

        account = self._get_verified_account(
            db=db,
            user_id=user_id,
        )

        checks.append(
            "MT5 account ownership verified"
        )

        managed_position, profile, live_position = (
            self._load_verified_position(
                db=db,
                user_id=user_id,
                account=account,
                position_ticket=position_ticket,
            )
        )

        checks.extend(
            [
                "Open reconciled managed position verified",
                "Management profile verified",
                "Live MT5 position refreshed",
                "Live MT5 ticket verified",
                "Live MT5 broker symbol verified",
                "Live MT5 direction verified",
            ]
        )

        if not profile.ai_management_enabled:
            raise AITradeManagementExecutionError(
                "AI management is disabled for this position."
            )

        live_volume = self._decimal(
            live_position["volume"],
            "live_volume",
        )

        if decision == self.DECISION_CLOSE_POSITION:
            requested_volume = live_volume
        else:
            if close_volume is None:
                raise AITradeManagementExecutionError(
                    "Partial close requires an explicit close volume."
                )

            requested_volume = self._decimal(
                close_volume,
                "close_volume",
            )

        info = self._get_symbol_info(
            managed_position.broker_symbol
        )

        checks.append(
            "Fresh MT5 broker symbol metadata loaded"
        )

        request, normalized_volume = (
            self._build_close_request(
                live_position=live_position,
                close_volume=requested_volume,
                info=info,
            )
        )

        checks.append(
            "Management close volume validated against "
            "live broker position"
        )

        checks.append(
            "Close request targets the existing MT5 position"
        )

        result, retcode, description = (
            self._execute_request(
                request=request,
                checks=checks,
                warnings=warnings,
            )
        )

        executed_volume = normalized_volume

        return AITradeManagementExecutionResult(
            executed=True,
            status="execution_reconciliation_required",
            decision=decision,
            user_id=user_id,
            managed_position_id=managed_position.id,
            position_ticket=position_ticket,
            broker_symbol=managed_position.broker_symbol,
            direction=managed_position.direction,
            requested_volume=requested_volume,
            executed_volume=executed_volume,
            requested_stop_loss=None,
            executed_stop_loss=None,
            requested_take_profit=None,
            executed_take_profit=None,
            broker_price=(
                self._decimal(
                    getattr(
                        result,
                        "price",
                        None,
                    ),
                    "executed_price",
                )
                if getattr(
                    result,
                    "price",
                    None,
                ) is not None
                else None
            ),
            retcode=retcode,
            retcode_description=description,
            checks=checks,
            warnings=warnings,
            errors=errors,
            message=(
                "AI trade-management close action was accepted "
                "by MT5. The live position must be reconciled "
                "before the management action is considered complete."
            ),
        )


ai_trade_management_execution_service = (
    AITradeManagementExecutionService()
)
