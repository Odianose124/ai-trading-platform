from __future__ import annotations
import multiprocessing
from datetime import datetime
from multiprocessing.connection import Connection
from threading import RLock
from typing import Any
from app.mt5.runtime import MT5AccountRuntime
from app.mt5.worker import MT5AccountWorker
class MT5WorkerProcessError(RuntimeError):
    """Raised when an MT5 worker process cannot be controlled safely."""
def _worker_process_entry(
    runtime: MT5AccountRuntime,
    connection: Connection,
    password: str,
) -> None:
    """
    Entry point executed inside the dedicated MT5 worker process.
    The MetaTrader5 Python module is loaded only inside this process.
    """
    worker = MT5AccountWorker(
        runtime,
        password,
    )
    try:
        worker.start()
        connection.send(
            {
                "type": "started",
                "status": worker.status(),
            }
        )
        while True:
            try:
                command = connection.recv()
            except EOFError:
                break
            if not isinstance(command, dict):
                connection.send(
                    {
                        "type": "error",
                        "error": "Invalid worker command.",
                    }
                )
                continue
            action = command.get("action")
            if action == "status":
                connection.send(
                    {
                        "type": "status",
                        "status": worker.status(),
                    }
                )
                continue
            if action == "get_positions":
                symbol = command.get("symbol")
                if symbol is not None and not isinstance(symbol, str):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The position symbol must be "
                                "a string or null."
                            ),
                        }
                    )
                    continue
                connection.send(
                    {
                        "type": "positions",
                        "positions": worker.get_positions(symbol),
                    }
                )
                continue
            if action == "get_position":
                ticket = command.get("ticket")
                try:
                    ticket = int(ticket)
                except (TypeError, ValueError):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The position ticket must be an integer."
                            ),
                        }
                    )
                    continue
                connection.send(
                    {
                        "type": "position",
                        "position": worker.get_position(ticket),
                    }
                )
                continue
            if action == "get_position_summary":
                connection.send(
                    {
                        "type": "position_summary",
                        "summary": worker.get_position_summary(),
                    }
                )
                continue
            if action == "get_history_order_position_ids":
                order_ticket = command.get("order_ticket")
                try:
                    order_ticket = int(order_ticket)
                except (TypeError, ValueError):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The order ticket must be an integer."
                            ),
                        }
                    )
                    continue
                connection.send(
                    {
                        "type": "history_order_position_ids",
                        "position_ids": (
                            worker.get_history_order_position_ids(
                                order_ticket
                            )
                        ),
                    }
                )
                continue
            if action == "get_history_order_deal_position_ids":
                order_ticket = command.get("order_ticket")
                try:
                    order_ticket = int(order_ticket)
                except (TypeError, ValueError):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The order ticket must be an integer."
                            ),
                        }
                    )
                    continue
                connection.send(
                    {
                        "type": "history_order_deal_position_ids",
                        "position_ids": (
                            worker.get_history_order_deal_position_ids(
                                order_ticket
                            )
                        ),
                    }
                )
                continue
            if action == "get_history_deal_position_id":
                deal_ticket = command.get("deal_ticket")
                date_from = command.get("date_from")
                date_to = command.get("date_to")
                try:
                    deal_ticket = int(deal_ticket)
                except (TypeError, ValueError):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The deal ticket must be an integer."
                            ),
                        }
                    )
                    continue
                if not isinstance(date_from, datetime):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The history start time must be a datetime."
                            ),
                        }
                    )
                    continue
                if not isinstance(date_to, datetime):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The history end time must be a datetime."
                            ),
                        }
                    )
                    continue
                connection.send(
                    {
                        "type": "history_deal_position_id",
                        "position_id": (
                            worker.get_history_deal_position_id(
                                deal_ticket,
                                date_from,
                                date_to,
                            )
                        ),
                    }
                )
                continue
            if action == "get_order_history":
                date_from = command.get("date_from")
                date_to = command.get("date_to")
                symbol = command.get("symbol")

                if date_from is not None and not isinstance(
                    date_from,
                    datetime,
                ):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The history start time must "
                                "be a datetime."
                            ),
                        }
                    )
                    continue

                if date_to is not None and not isinstance(
                    date_to,
                    datetime,
                ):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The history end time must "
                                "be a datetime."
                            ),
                        }
                    )
                    continue

                if symbol is not None and not isinstance(
                    symbol,
                    str,
                ):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The history symbol must "
                                "be a string or null."
                            ),
                        }
                    )
                    continue

                try:
                    result = worker.get_order_history(
                        date_from=date_from,
                        date_to=date_to,
                        symbol=symbol,
                    )
                except Exception as exc:
                    connection.send(
                        {
                            "type": "error",
                            "error": str(exc),
                        }
                    )
                    continue

                connection.send(
                    {
                        "type": "order_history",
                        "history": result,
                    }
                )
                continue

            if action == "get_pending_orders":
                symbol = command.get("symbol")

                if (
                    symbol is not None
                    and not isinstance(symbol, str)
                ):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The pending-order symbol must be "
                                "a string or null."
                            ),
                        }
                    )
                    continue

                try:
                    result = worker.get_pending_orders(
                        symbol
                    )
                except Exception as exc:
                    connection.send(
                        {
                            "type": "error",
                            "error": str(exc),
                        }
                    )
                    continue

                connection.send(
                    {
                        "type": "pending_orders",
                        "pending_orders": result,
                    }
                )
                continue

            if action == "cancel_pending_order":
                ticket = command.get("ticket")

                try:
                    ticket = int(ticket)
                except (TypeError, ValueError):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The pending-order ticket must "
                                "be an integer."
                            ),
                        }
                    )
                    continue

                try:
                    result = worker.cancel_pending_order(
                        ticket
                    )
                except Exception as exc:
                    connection.send(
                        {
                            "type": "error",
                            "error": str(exc),
                        }
                    )
                    continue

                connection.send(
                    {
                        "type": "pending_order_cancel_result",
                        "result": result,
                    }
                )
                continue

            if action == "modify_pending_order":
                ticket = command.get("ticket")
                price = command.get("price")
                stop_loss = command.get("stop_loss")
                take_profit = command.get("take_profit")

                try:
                    ticket = int(ticket)
                except (TypeError, ValueError):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The pending-order ticket must "
                                "be an integer."
                            ),
                        }
                    )
                    continue

                try:
                    result = worker.modify_pending_order(
                        ticket=ticket,
                        price=price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                    )
                except Exception as exc:
                    connection.send(
                        {
                            "type": "error",
                            "error": str(exc),
                        }
                    )
                    continue

                connection.send(
                    {
                        "type": "pending_order_modify_result",
                        "result": result,
                    }
                )
                continue

            if action == "validate_trade":
                symbol = command.get("symbol")
                direction = command.get("direction")
                volume = command.get("volume")
                entry_price = command.get("entry_price")
                stop_loss = command.get("stop_loss")
                take_profit = command.get("take_profit")
                order_type = command.get("order_type")
                if not isinstance(symbol, str) or not symbol.strip():
                    connection.send(
                        {
                            "type": "error",
                            "error": "The validation symbol is required.",
                        }
                    )
                    continue
                if not isinstance(direction, str) or not direction.strip():
                    connection.send(
                        {
                            "type": "error",
                            "error": "The validation direction is required.",
                        }
                    )
                    continue
                connection.send(
                    {
                        "type": "trade_validation",
                        "result": worker.validate_trade(
                            symbol=symbol,
                            direction=direction,
                            volume=volume,
                            entry_price=entry_price,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                            order_type=order_type,
                        ),
                    }
                )
                continue
            if action == "order_check":
                request = command.get("request")
                if not isinstance(request, dict):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The order check request must be an object."
                            ),
                        }
                    )
                    continue
                try:
                    result = worker.order_check(request)
                except Exception as exc:
                    connection.send(
                        {
                            "type": "error",
                            "error": str(exc),
                        }
                    )
                    continue
                connection.send(
                    {
                        "type": "order_check_result",
                        "result": result,
                    }
                )
                continue
            if action == "execute_order":
                request = command.get("request")
                if not isinstance(request, dict):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The order request must be an object."
                            ),
                        }
                    )
                    continue
                try:
                    result = worker.execute_order(request)
                except Exception as exc:
                    connection.send(
                        {
                            "type": "error",
                            "error": str(exc),
                        }
                    )
                    continue
                connection.send(
                    {
                        "type": "order_result",
                        "result": result,
                    }
                )
                continue
            if action == "symbol_info":
                symbol = command.get("symbol")
                try:
                    result = worker.symbol_info(symbol)
                except Exception as exc:
                    connection.send(
                        {
                            "type": "error",
                            "error": str(exc),
                        }
                    )
                    continue
                connection.send(
                    {
                        "type": "symbol_info_result",
                        "result": result,
                    }
                )
                continue
            if action == "symbol_info_tick":
                symbol = command.get("symbol")
                try:
                    result = worker.symbol_info_tick(symbol)
                except Exception as exc:
                    connection.send(
                        {
                            "type": "error",
                            "error": str(exc),
                        }
                    )
                    continue
                connection.send(
                    {
                        "type": "symbol_info_tick_result",
                        "result": result,
                    }
                )
                continue
            if action == "account_info":
                try:
                    result = worker.account_info()
                except Exception as exc:
                    connection.send(
                        {
                            "type": "error",
                            "error": str(exc),
                        }
                    )
                    continue
                connection.send(
                    {
                        "type": "account_info_result",
                        "result": result,
                    }
                )
                continue
            if action == "order_calc_margin":
                request = command.get("request")
                if not isinstance(request, dict):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The margin request must be an object."
                            ),
                        }
                    )
                    continue
                try:
                    result = worker.order_calc_margin(request)
                except Exception as exc:
                    connection.send(
                        {
                            "type": "error",
                            "error": str(exc),
                        }
                    )
                    continue
                connection.send(
                    {
                        "type": "order_calc_margin_result",
                        "result": result,
                    }
                )
                continue
            if action == "stop":
                worker.stop()
                connection.send(
                    {
                        "type": "stopped",
                    }
                )
                break
            connection.send(
                {
                    "type": "error",
                    "error": f"Unsupported worker action: {action}",
                }
            )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception(
            "MT5 worker process failed | mt5_account_id=%s",
            runtime.mt5_account_id,
        )
        try:
            connection.send(
                {
                    "type": "error",
                    "error": str(exc),
                }
            )
        except (BrokenPipeError, EOFError, OSError):
            pass
        return
    finally:
        try:
            worker.stop()
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Failed to cleanly stop MT5 worker | mt5_account_id=%s",
                runtime.mt5_account_id,
            )
        try:
            connection.close()
        except OSError:
            pass
class MT5WorkerProcess:
    """
    Parent-process controller for one account-scoped MT5 worker.
    Exactly one MT5AccountRuntime is associated with this process.
    """
    def __init__(
        self,
        runtime: MT5AccountRuntime,
        password: str,
    ) -> None:
        self.runtime = runtime
        self._password = password
        self._process: multiprocessing.Process | None = None
        self._connection: Connection | None = None
        self._lock = RLock()
    @property
    def process(self) -> multiprocessing.Process | None:
        return self._process
    def start(self) -> dict[str, Any]:
        with self._lock:
            if self.is_running():
                return self.status()
            self.runtime.validate()
            parent_connection, child_connection = (
                multiprocessing.Pipe()
            )
            process = multiprocessing.Process(
                target=_worker_process_entry,
                args=(
                    self.runtime,
                    child_connection,
                    self._password,
                ),
                name=(
                    f"mt5-worker-"
                    f"{self.runtime.mt5_account_id}"
                ),
                daemon=True,
            )
            process.start()
            child_connection.close()
            self._process = process
            self._connection = parent_connection
            try:
                response = self._receive_response()
            except Exception:
                self._cleanup_failed_start()
                raise
            if response.get("type") == "error":
                self._cleanup_failed_start()
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker failed to start.",
                    )
                )
            if response.get("type") != "started":
                self._cleanup_failed_start()
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected startup response."
                )
            return self._serialize_status(
                response.get("status")
            )
    def status(self) -> dict[str, Any]:
        with self._lock:
            if not self.is_running():
                return {
                    "running": False,
                    "mt5_account_id": self.runtime.mt5_account_id,
                    "user_id": self.runtime.user_id,
                    "login": self.runtime.login,
                    "server": self.runtime.server,
                    "connected": False,
                    "terminal_running": False,
                }
            self._send_command(
                {
                    "action": "status",
                }
            )
            response = self._receive_response()
            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker status request failed.",
                    )
                )
            if response.get("type") != "status":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected status response."
                )
            return self._serialize_status(
                response.get("status")
            )
    def get_positions(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Request account-scoped positions from the dedicated worker.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )
            normalized_symbol = (
                symbol.strip().upper()
                if symbol
                else None
            )
            self._send_command(
                {
                    "action": "get_positions",
                    "symbol": normalized_symbol,
                }
            )
            response = self._receive_response()
            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker position request failed.",
                    )
                )
            if response.get("type") != "positions":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected position response."
                )
            positions = response.get("positions")
            if not isinstance(positions, list):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid positions payload."
                )
            return positions
    def get_order_history(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        """
        Request account-scoped MT5 order/deal history.
        """

        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )

            normalized_symbol = (
                symbol.strip().upper()
                if symbol
                else None
            )

            self._send_command(
                {
                    "action": "get_order_history",
                    "date_from": date_from,
                    "date_to": date_to,
                    "symbol": normalized_symbol,
                }
            )

            response = self._receive_response()

            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 order-history request failed.",
                    )
                )

            if response.get("type") != "order_history":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "order-history response."
                )

            history = response.get("history")

            if not isinstance(history, dict):
                raise MT5WorkerProcessError(
                    "MT5 worker returned invalid order-history data."
                )

            return history

    def get_pending_orders(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Request account-scoped pending orders from the dedicated worker.
        """

        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )

            normalized_symbol = (
                symbol.strip().upper()
                if symbol
                else None
            )

            self._send_command(
                {
                    "action": "get_pending_orders",
                    "symbol": normalized_symbol,
                }
            )

            response = self._receive_response()

            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 pending-order request failed.",
                    )
                )

            if response.get("type") != "pending_orders":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "pending-order response."
                )

            pending_orders = response.get(
                "pending_orders",
                [],
            )

            if not isinstance(
                pending_orders,
                list,
            ):
                raise MT5WorkerProcessError(
                    "MT5 worker returned invalid pending-order data."
                )

            return pending_orders

    def cancel_pending_order(
        self,
        ticket: int,
    ) -> dict[str, Any]:
        """
        Request cancellation of one account-scoped pending order.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )

            try:
                normalized_ticket = int(ticket)
            except (TypeError, ValueError) as exc:
                raise MT5WorkerProcessError(
                    "Pending-order ticket must be an integer."
                ) from exc

            self._send_command(
                {
                    "action": "cancel_pending_order",
                    "ticket": normalized_ticket,
                }
            )

            response = self._receive_response()

            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 pending-order cancellation failed.",
                    )
                )

            if response.get("type") != "pending_order_cancel_result":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "pending-order cancellation response."
                )

            result = response.get("result")

            if not isinstance(result, dict):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid "
                    "pending-order cancellation result."
                )

            return result

    def modify_pending_order(
        self,
        ticket: int,
        price: Any = None,
        stop_loss: Any = None,
        take_profit: Any = None,
    ) -> dict[str, Any]:
        """
        Request modification of one account-scoped pending order.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )

            try:
                normalized_ticket = int(ticket)
            except (TypeError, ValueError) as exc:
                raise MT5WorkerProcessError(
                    "Pending-order ticket must be an integer."
                ) from exc

            self._send_command(
                {
                    "action": "modify_pending_order",
                    "ticket": normalized_ticket,
                    "price": price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                }
            )

            response = self._receive_response()

            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 pending-order modification failed.",
                    )
                )

            if response.get("type") != "pending_order_modify_result":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "pending-order modification response."
                )

            result = response.get("result")

            if not isinstance(result, dict):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid "
                    "pending-order modification result."
                )

            return result

    def get_position(
        self,
        ticket: int,
    ) -> dict[str, Any] | None:
        """
        Request one account-scoped position from the dedicated worker.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )
            try:
                normalized_ticket = int(ticket)
            except (TypeError, ValueError) as exc:
                raise MT5WorkerProcessError(
                    "Position ticket must be an integer."
                ) from exc
            self._send_command(
                {
                    "action": "get_position",
                    "ticket": normalized_ticket,
                }
            )
            response = self._receive_response()
            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker position request failed.",
                    )
                )
            if response.get("type") != "position":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "single-position response."
                )
            position = response.get("position")
            if position is not None and not isinstance(
                position,
                dict,
            ):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid position payload."
                )
            return position
    def get_position_summary(self) -> dict[str, Any]:
        """
        Request an account-scoped position summary.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )
            self._send_command(
                {
                    "action": "get_position_summary",
                }
            )
            response = self._receive_response()
            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker position summary request failed.",
                    )
                )
            if response.get("type") != "position_summary":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "position summary response."
                )
            summary = response.get("summary")
            if not isinstance(summary, dict):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid position summary."
                )
            return summary
    def get_history_order_position_ids(
        self,
        order_ticket: int,
    ) -> list[int]:
        """
        Request position identities from an MT5 order history record.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )
            try:
                normalized_ticket = int(order_ticket)
            except (TypeError, ValueError) as exc:
                raise MT5WorkerProcessError(
                    "Order ticket must be an integer."
                ) from exc
            self._send_command(
                {
                    "action": "get_history_order_position_ids",
                    "order_ticket": normalized_ticket,
                }
            )
            response = self._receive_response()
            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker order history request failed.",
                    )
                )
            if response.get("type") != "history_order_position_ids":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "order history response."
                )
            position_ids = response.get("position_ids")
            if not isinstance(position_ids, list):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid order "
                    "history position ID payload."
                )
            return [
                int(position_id)
                for position_id in position_ids
            ]
    def get_history_order_deal_position_ids(
        self,
        order_ticket: int,
    ) -> list[int]:
        """
        Request position identities from deals belonging to an order.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )
            try:
                normalized_ticket = int(order_ticket)
            except (TypeError, ValueError) as exc:
                raise MT5WorkerProcessError(
                    "Order ticket must be an integer."
                ) from exc
            self._send_command(
                {
                    "action": "get_history_order_deal_position_ids",
                    "order_ticket": normalized_ticket,
                }
            )
            response = self._receive_response()
            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker deal history request failed.",
                    )
                )
            if response.get("type") != "history_order_deal_position_ids":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "order deal history response."
                )
            position_ids = response.get("position_ids")
            if not isinstance(position_ids, list):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid order deal "
                    "history position ID payload."
                )
            return [
                int(position_id)
                for position_id in position_ids
            ]
    def get_history_deal_position_id(
        self,
        deal_ticket: int,
        date_from: datetime,
        date_to: datetime,
    ) -> int | None:
        """
        Request the position identity for a deal inside an execution
        history window.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )
            try:
                normalized_ticket = int(deal_ticket)
            except (TypeError, ValueError) as exc:
                raise MT5WorkerProcessError(
                    "Deal ticket must be an integer."
                ) from exc
            if not isinstance(date_from, datetime):
                raise MT5WorkerProcessError(
                    "History start time must be a datetime."
                )
            if not isinstance(date_to, datetime):
                raise MT5WorkerProcessError(
                    "History end time must be a datetime."
                )
            self._send_command(
                {
                    "action": "get_history_deal_position_id",
                    "deal_ticket": normalized_ticket,
                    "date_from": date_from,
                    "date_to": date_to,
                }
            )
            response = self._receive_response()
            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker deal history request failed.",
                    )
                )
            if response.get("type") != "history_deal_position_id":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "deal history response."
                )
            position_id = response.get("position_id")
            if position_id is None:
                return None
            try:
                return int(position_id)
            except (TypeError, ValueError) as exc:
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid deal position ID."
                ) from exc
    def symbol_info(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """
        Request symbol information from the account-specific MT5 worker.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )

            self._send_command(
                {
                    "action": "symbol_info",
                    "symbol": symbol,
                }
            )

            response = self._receive_response()

            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker symbol information request failed.",
                    )
                )

            if response.get("type") != "symbol_info_result":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "symbol information response."
                )

            result = response.get("result")

            if not isinstance(result, dict):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid symbol information payload."
                )

            return result

    def symbol_info_tick(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """
        Request current symbol tick information from the
        account-specific MT5 worker.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )

            self._send_command(
                {
                    "action": "symbol_info_tick",
                    "symbol": symbol,
                }
            )

            response = self._receive_response()

            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker symbol tick request failed.",
                    )
                )

            if response.get("type") != "symbol_info_tick_result":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "symbol tick response."
                )

            result = response.get("result")

            if not isinstance(result, dict):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid "
                    "symbol tick payload."
                )

            return result

    def account_info(
        self,
    ) -> dict[str, Any]:
        """
        Request account information from the account-specific MT5 worker.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )

            self._send_command(
                {
                    "action": "account_info",
                }
            )

            response = self._receive_response()

            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker account information request failed.",
                    )
                )

            if response.get("type") != "account_info_result":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "account information response."
                )

            result = response.get("result")

            if not isinstance(result, dict):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid "
                    "account information payload."
                )

            return result
    def order_calc_margin(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Request broker margin calculation from the account-specific
        MT5 worker.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )

            if not isinstance(request, dict):
                raise MT5WorkerProcessError(
                    "The margin calculation request must be an object."
                )

            self._send_command(
                {
                    "action": "order_calc_margin",
                    "request": request,
                }
            )

            response = self._receive_response()

            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker margin calculation failed.",
                    )
                )

            if response.get("type") != "order_calc_margin_result":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "margin calculation response."
                )

            result = response.get("result")

            if not isinstance(result, dict):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid "
                    "margin calculation result."
                )

            return result
    def validate_trade(
        self,
        *,
        symbol: str,
        direction: str,
        volume: Any,
        entry_price: Any = None,
        stop_loss: Any = None,
        take_profit: Any = None,
        order_type: Any = None,
    ) -> dict[str, Any]:
        """
        Run broker validation inside the account-specific worker.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )
            self._send_command(
                {
                    "action": "validate_trade",
                    "symbol": symbol,
                    "direction": direction,
                    "volume": volume,
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "order_type": order_type,
                }
            )
            response = self._receive_response()
            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker broker validation failed.",
                    )
                )
            if response.get("type") != "trade_validation":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "trade validation response."
                )
            result = response.get("result")
            if not isinstance(result, dict):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid "
                    "trade validation payload."
                )
            return result
    def execute_order(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute an order through the dedicated account worker.
        """
        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )
            if not isinstance(request, dict):
                raise MT5WorkerProcessError(
                    "The order request must be an object."
                )
            self._send_command(
                {
                    "action": "execute_order",
                    "request": request,
                }
            )
            response = self._receive_response()
            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker order execution failed.",
                    )
                )
            if response.get("type") != "order_result":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "order execution response."
                )
            result = response.get("result")
            if not isinstance(result, dict):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid order result."
                )
            return result
    def stop(self) -> None:
        with self._lock:
            process = self._process
            if process is None:
                return
            if process.is_alive():
                try:
                    self._send_command(
                        {
                            "action": "stop",
                        }
                    )
                    self._receive_response()
                except (
                    BrokenPipeError,
                    EOFError,
                    OSError,
                    MT5WorkerProcessError,
                ):
                    import logging
                    logging.getLogger(__name__).warning(
                        "MT5 worker stopped without a normal response | "
                        "mt5_account_id=%s",
                        self.runtime.mt5_account_id,
                    )
            process.join(timeout=15)
            if process.is_alive():
                import logging
                logging.getLogger(__name__).warning(
                    "Terminating unresponsive MT5 worker | "
                    "mt5_account_id=%s",
                    self.runtime.mt5_account_id,
                )
                process.terminate()
                process.join(timeout=5)
            self._close_connection()
            self._process = None
            self._connection = None
    def is_running(self) -> bool:
        process = self._process
        return (
            process is not None
            and process.is_alive()
        )
    def _send_command(
        self,
        command: dict[str, Any],
    ) -> None:
        connection = self._connection
        if connection is None:
            raise MT5WorkerProcessError(
                "MT5 worker IPC connection is not available."
            )
        try:
            connection.send(command)
        except (BrokenPipeError, EOFError, OSError) as exc:
            raise MT5WorkerProcessError(
                "Unable to communicate with the MT5 worker process."
            ) from exc
    def _receive_response(self) -> dict[str, Any]:
        connection = self._connection
        if connection is None:
            raise MT5WorkerProcessError(
                "MT5 worker IPC connection is not available."
            )
        try:
            response = connection.recv()
        except (EOFError, OSError) as exc:
            raise MT5WorkerProcessError(
                "MT5 worker process closed the IPC connection."
            ) from exc
        if not isinstance(response, dict):
            raise MT5WorkerProcessError(
                "MT5 worker returned an invalid response."
            )
        return response
    def _serialize_status(
        self,
        status: Any,
    ) -> dict[str, Any]:
        if status is None:
            raise MT5WorkerProcessError(
                "MT5 worker returned no status."
            )
        if hasattr(status, "__dict__"):
            values = vars(status)
        elif isinstance(status, dict):
            values = status
        else:
            raise MT5WorkerProcessError(
                "MT5 worker returned an invalid status object."
            )
        return {
            "running": self.is_running(),
            **values,
        }
    def _cleanup_failed_start(self) -> None:
        process = self._process
        if process is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        self._close_connection()
        self._process = None
        self._connection = None
    def _close_connection(self) -> None:
        connection = self._connection
        if connection is None:
            return
        try:
            connection.close()
        except OSError:
            pass
def create_worker_process(
    runtime: MT5AccountRuntime,
) -> MT5WorkerProcess:
    return MT5WorkerProcess(runtime)





