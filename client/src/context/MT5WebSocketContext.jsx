import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

const MT5WebSocketContext = createContext(null);

const ACCESS_TOKEN_KEY = "ai_trading_access_token";
const RECONNECT_BASE_DELAY = 1000;
const RECONNECT_MAX_DELAY = 10000;

function buildWebSocketUrl(token) {
  const apiUrl = import.meta.env.VITE_API_URL;

  if (!apiUrl) {
    throw new Error(
      "VITE_API_URL is not configured.",
    );
  }

  const url = new URL(apiUrl);

  url.protocol =
    url.protocol === "https:"
      ? "wss:"
      : "ws:";

  url.pathname = "/ws/mt5";
  url.search = "";

  url.searchParams.set("token", token);

  return url.toString();
}

export function MT5WebSocketProvider({
  children,
}) {
  const websocketRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const reconnectAttemptRef = useRef(0);
  const mountedRef = useRef(true);

  const [status, setStatus] = useState(
    "disconnected",
  );
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState(null);

  const requestedSymbolsRef = useRef([]);

  const sendTickSubscription = useCallback(
    (symbols) => {
      if (!Array.isArray(symbols)) {
        return;
      }

      const normalizedSymbols = [];

      for (const symbol of symbols) {
        if (typeof symbol !== "string") {
          continue;
        }

        const value = symbol.trim().toUpperCase();

        if (
          value &&
          !normalizedSymbols.includes(value)
        ) {
          normalizedSymbols.push(value);
        }
      }

      requestedSymbolsRef.current =
        normalizedSymbols;

      const websocket =
        websocketRef.current;

      if (
        !websocket ||
        websocket.readyState !== WebSocket.OPEN
      ) {
        return;
      }

      websocket.send(
        JSON.stringify({
          type: "subscribe_ticks",
          symbols: normalizedSymbols,
        }),
      );
    },
    [],
  );

  const subscribeTicks = useCallback(
    (symbols) => {
      sendTickSubscription(symbols);
    },
    [sendTickSubscription],
  );

  useEffect(() => {
    mountedRef.current = true;

    function clearReconnectTimer() {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(
          reconnectTimerRef.current,
        );

        reconnectTimerRef.current = null;
      }
    }

    function closeSocket() {
      const websocket =
        websocketRef.current;

      websocketRef.current = null;

      if (!websocket) {
        return;
      }

      websocket.onopen = null;
      websocket.onmessage = null;
      websocket.onerror = null;
      websocket.onclose = null;

      try {
        websocket.close();
      } catch {
        // The socket may already be closed.
      }
    }

    function scheduleReconnect() {
      if (!mountedRef.current) {
        return;
      }

      clearReconnectTimer();

      const attempt =
        reconnectAttemptRef.current;

      const delay = Math.min(
        RECONNECT_BASE_DELAY *
          2 ** attempt,
        RECONNECT_MAX_DELAY,
      );

      reconnectAttemptRef.current =
        Math.min(attempt + 1, 4);

      reconnectTimerRef.current =
        window.setTimeout(() => {
          reconnectTimerRef.current = null;
          connect();
        }, delay);
    }

    function connect() {
      if (!mountedRef.current) {
        return;
      }

      const token = localStorage.getItem(
        ACCESS_TOKEN_KEY,
      );

      if (!token) {
        setStatus("disconnected");
        setError(null);
        return;
      }

      const existingSocket =
        websocketRef.current;

      if (
        existingSocket &&
        (
          existingSocket.readyState ===
            WebSocket.OPEN ||
          existingSocket.readyState ===
            WebSocket.CONNECTING
        )
      ) {
        return;
      }

      let websocketUrl;

      try {
        websocketUrl =
          buildWebSocketUrl(token);
      } catch (connectionError) {
        setStatus("error");
        setError(
          connectionError?.message ||
            "Unable to create the MT5 WebSocket URL.",
        );
        return;
      }

      setStatus("connecting");
      setError(null);

      const websocket =
        new WebSocket(websocketUrl);

      websocketRef.current = websocket;

      websocket.onopen = () => {
        if (!mountedRef.current) {
          return;
        }

        reconnectAttemptRef.current = 0;
        setStatus("connected");
        setError(null);

        const requestedSymbols =
          requestedSymbolsRef.current;

        if (requestedSymbols.length) {
          websocket.send(
            JSON.stringify({
              type: "subscribe_ticks",
              symbols: requestedSymbols,
            }),
          );
        }
      };

      websocket.onmessage = (event) => {
        if (!mountedRef.current) {
          return;
        }

        try {
          const message =
            JSON.parse(event.data);

          if (
            message?.type ===
            "mt5_snapshot"
          ) {
            setSnapshot(message);
            setError(null);
            return;
          }


          if (
            message?.type ===
            "mt5_tick"
          ) {
            const tick =
              message?.data;

            if (
              !tick ||
              typeof tick !== "object"
            ) {
              return;
            }

            const brokerSymbol =
              typeof tick.symbol === "string"
                ? tick.symbol.trim().toUpperCase()
                : "";

            if (!brokerSymbol) {
              return;
            }

            setSnapshot((current) => {
              if (!current) {
                return current;
              }

              return {
                ...current,
                ticks: {
                  ...(current.ticks || {}),
                  [brokerSymbol]: tick,
                },
              };
            });

            return;
          }

          if (
            message?.type ===
            "mt5_tick_subscription"
          ) {
            return;
          }

          if (
            message?.type ===
              "mt5_snapshot_error" ||
            message?.type ===
              "mt5_error"
          ) {
            const messageError =
              message?.detail ||
              message?.error ||
              message?.message ||
              "MT5 WebSocket error.";

            setError(messageError);
          }
        } catch {
          setError(
            "Received an invalid MT5 WebSocket message.",
          );
        }
      };

      websocket.onerror = () => {
        if (!mountedRef.current) {
          return;
        }

        setStatus("error");
        setError(
          "MT5 WebSocket connection error.",
        );
      };

      websocket.onclose = (event) => {
        if (!mountedRef.current) {
          return;
        }

        websocketRef.current = null;

        setStatus("disconnected");

        if (
          event.code === 1008
        ) {
          setError(
            "MT5 WebSocket authentication was rejected.",
          );
          return;
        }

        scheduleReconnect();
      };
    }

    connect();

    return () => {
      mountedRef.current = false;

      clearReconnectTimer();
      closeSocket();
    };
  }, []);

  const connection =
    snapshot?.connection ?? null;

  const account =
    snapshot?.account ?? null;

  const positions =
    snapshot?.positions ?? [];

  const pendingOrders =
    snapshot?.pending_orders ?? [];

  const summary =
    snapshot?.summary ?? null;

  const ticks =
    snapshot?.ticks ?? {};

  const timestamp =
    snapshot?.timestamp ?? null;

  const mt5AccountId =
    snapshot?.mt5_account_id ?? null;

  const userId =
    snapshot?.user_id ?? null;

  const value = useMemo(
    () => ({
      status,
      connected:
        status === "connected",
      connecting:
        status === "connecting",
      snapshot,
      connection,
      account,
      positions,
      pendingOrders,
      summary,
      ticks,
      timestamp,
      mt5AccountId,
      userId,
      error,
      subscribeTicks,
    }),
    [
      status,
      snapshot,
      connection,
      account,
      positions,
      pendingOrders,
      summary,
      ticks,
      timestamp,
      mt5AccountId,
      userId,
      error,
      subscribeTicks,
    ],
  );

  return (
    <MT5WebSocketContext.Provider
      value={value}
    >
      {children}
    </MT5WebSocketContext.Provider>
  );
}

export function useMT5WebSocket() {
  const context = useContext(
    MT5WebSocketContext,
  );

  if (!context) {
    throw new Error(
      "useMT5WebSocket must be used inside MT5WebSocketProvider.",
    );
  }

  return context;
}

