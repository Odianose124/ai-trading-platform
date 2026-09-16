import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  LoaderCircle,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import api from "./services/api";

const DEFAULT_FORM = {
  symbol: "XAUUSD",
  direction: "buy",
  entry: "",
  stopLoss: "",
  takeProfit: "",
  volume: "0.01",
  riskPercent: "1",
  aiManagementEnabled: true,
};

function ManualTradeSetup() {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [preview, setPreview] = useState(null);
  const [intent, setIntent] = useState(null);
  const [confirmation, setConfirmation] = useState(null);

  const [previewLoading, setPreviewLoading] = useState(false);
  const [intentLoading, setIntentLoading] = useState(false);
  const [confirmationLoading, setConfirmationLoading] =
    useState(false);

  const [error, setError] = useState("");

  const isComplete = useMemo(() => {
    return (
      form.symbol.trim() !== "" &&
      Number(form.entry) > 0 &&
      Number(form.stopLoss) > 0 &&
      Number(form.takeProfit) > 0 &&
      Number(form.volume) > 0 &&
      Number(form.riskPercent) > 0
    );
  }, [form]);

  function updateField(field, value) {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));

    setPreview(null);
    setIntent(null);
    setConfirmation(null);
    setError("");
  }

  async function previewTrade(event) {
    event.preventDefault();

    if (!isComplete || previewLoading) {
      return;
    }

    setPreviewLoading(true);
    setPreview(null);
    setIntent(null);
    setConfirmation(null);
    setError("");

    try {
      const response = await api.post(
        "/api/execution/preview",
        {
          symbol: form.symbol.trim().toUpperCase(),
          direction: form.direction,
          volume: Number(form.volume),
          signal_entry_price: Number(form.entry),
          stop_loss: Number(form.stopLoss),
          take_profit: Number(form.takeProfit),
          risk_percent: Number(form.riskPercent),
        },
      );

      setPreview(response.data);
    } catch (requestError) {
      setError(
        requestError?.response?.data?.detail ||
          requestError?.response?.data?.message ||
          "Unable to validate the manual trade.",
      );
    } finally {
      setPreviewLoading(false);
    }
  }

  async function createIntent() {
    if (!preview?.approved || intentLoading) {
      return;
    }

    setIntentLoading(true);
    setError("");

    try {
      const response = await api.post(
        "/api/trade-intents",
        {
          symbol: form.symbol.trim().toUpperCase(),
          broker_symbol: preview.broker_symbol,
          direction: form.direction,
          volume: Number(form.volume),
          signal_entry_price: Number(form.entry),
          execution_price: Number(preview.execution_price),
          stop_loss: Number(form.stopLoss),
          take_profit: Number(form.takeProfit),
          risk_percent: Number(form.riskPercent),
          ai_management_enabled:
            form.aiManagementEnabled,
          signal_price_deviation_percent:
            preview.signal_price_deviation_percent ??
            null,
          margin_required:
            preview.margin?.required ?? null,
          free_margin:
            preview.margin?.free ?? null,
          preview_status:
            preview.status ||
            "ready_for_confirmation",
          warnings: preview.warnings || [],
        },
      );

      setIntent(response.data);
    } catch (requestError) {
      setError(
        requestError?.response?.data?.detail ||
          requestError?.response?.data?.message ||
          "Unable to create the trade intent.",
      );
    } finally {
      setIntentLoading(false);
    }
  }

  async function confirmTrade() {
    const intentId =
      intent?.intent_id ??
      intent?.id ??
      null;

    if (!intentId || confirmationLoading) {
      return;
    }

    setConfirmationLoading(true);
    setError("");

    try {
      const response = await api.post(
        "/api/trade-confirmation",
        {
          intent_id: Number(intentId),
        },
      );

      setConfirmation(response.data);
    } catch (requestError) {
      setError(
        requestError?.response?.data?.detail ||
          requestError?.response?.data?.message ||
          "Unable to confirm the manual trade.",
      );
    } finally {
      setConfirmationLoading(false);
    }
  }

  function resetTrade() {
    setForm(DEFAULT_FORM);
    setPreview(null);
    setIntent(null);
    setConfirmation(null);
    setError("");
  }

  return (
    <section
      className="trading-panel"
      style={{ marginBottom: 24 }}
    >
      <div className="trading-panel-header">
        <div>
          <span>Manual execution</span>
          <h2>Open a manual trade</h2>
        </div>

        <div className="trade-review-lock">
          <ShieldCheck size={17} />
          Protected execution
        </div>
      </div>

      <div className="trade-review-intro">
        <ShieldCheck size={20} />

        <div>
          <strong>You control the trade setup</strong>

          <span>
            Enter your own trade. The platform validates
            it against the live MT5 broker environment
            before any order can be sent.
          </span>
        </div>
      </div>

      <form onSubmit={previewTrade}>
        <div className="trade-review-input-grid">
          <label className="trade-review-field">
            <span>Symbol</span>

            <input
              value={form.symbol}
              onChange={(event) =>
                updateField(
                  "symbol",
                  event.target.value,
                )
              }
              placeholder="XAUUSD"
              autoComplete="off"
            />
          </label>

          <div className="trade-review-field">
            <span>Direction</span>

            <div
              style={{
                display: "flex",
                gap: 8,
              }}
            >
              <button
                type="button"
                className="trade-review-preview-button"
                style={{
                  flex: 1,
                  opacity:
                    form.direction === "buy"
                      ? 1
                      : 0.55,
                }}
                onClick={() =>
                  updateField(
                    "direction",
                    "buy",
                  )
                }
              >
                <ArrowUp size={17} />
                BUY
              </button>

              <button
                type="button"
                className="trade-review-preview-button"
                style={{
                  flex: 1,
                  opacity:
                    form.direction === "sell"
                      ? 1
                      : 0.55,
                }}
                onClick={() =>
                  updateField(
                    "direction",
                    "sell",
                  )
                }
              >
                <ArrowDown size={17} />
                SELL
              </button>
            </div>
          </div>

          <label className="trade-review-field">
            <span>Entry price</span>

            <input
              type="number"
              min="0"
              step="any"
              value={form.entry}
              onChange={(event) =>
                updateField(
                  "entry",
                  event.target.value,
                )
              }
              placeholder="Your entry price"
              inputMode="decimal"
            />
          </label>

          <label className="trade-review-field">
            <span>Stop loss</span>

            <input
              type="number"
              min="0"
              step="any"
              value={form.stopLoss}
              onChange={(event) =>
                updateField(
                  "stopLoss",
                  event.target.value,
                )
              }
              placeholder="Protective stop"
              inputMode="decimal"
            />
          </label>

          <label className="trade-review-field">
            <span>Take profit</span>

            <input
              type="number"
              min="0"
              step="any"
              value={form.takeProfit}
              onChange={(event) =>
                updateField(
                  "takeProfit",
                  event.target.value,
                )
              }
              placeholder="Profit target"
              inputMode="decimal"
            />
          </label>

          <label className="trade-review-field">
            <span>Volume</span>

            <input
              type="number"
              min="0.01"
              step="0.01"
              value={form.volume}
              onChange={(event) =>
                updateField(
                  "volume",
                  event.target.value,
                )
              }
              inputMode="decimal"
            />
          </label>

          <label className="trade-review-field">
            <span>Risk %</span>

            <input
              type="number"
              min="0.01"
              max="100"
              step="0.01"
              value={form.riskPercent}
              onChange={(event) =>
                updateField(
                  "riskPercent",
                  event.target.value,
                )
              }
              inputMode="decimal"
            />
          </label>

          <div className="trade-review-field readonly">
            <span>AI management</span>

            <button
              type="button"
              className="trade-review-preview-button"
              onClick={() =>
                updateField(
                  "aiManagementEnabled",
                  !form.aiManagementEnabled,
                )
              }
            >
              <ShieldCheck size={17} />

              {form.aiManagementEnabled
                ? "ON"
                : "OFF"}
            </button>
          </div>
        </div>

        <button
          type="submit"
          className="trade-review-preview-button"
          disabled={!isComplete || previewLoading}
          style={{ marginTop: 18 }}
        >
          {previewLoading ? (
            <>
              <LoaderCircle
                size={18}
                className="spin"
              />
              Validating with broker...
            </>
          ) : (
            <>
              <ShieldCheck size={18} />
              Review manual trade
            </>
          )}
        </button>
      </form>

      {error && (
        <div
          className="trade-review-result error"
          style={{ marginTop: 18 }}
        >
          <AlertTriangle size={19} />

          <div>
            <strong>
              Trade action blocked
            </strong>

            <span>{error}</span>
          </div>
        </div>
      )}

      {preview && (
        <div
          className={`trade-review-result ${
            preview.approved
              ? "approved"
              : "blocked"
          }`}
          style={{ marginTop: 18 }}
        >
          {preview.approved ? (
            <CheckCircle2 size={21} />
          ) : (
            <XCircle size={21} />
          )}

          <div>
            <strong>
              {preview.approved
                ? "TRADE PASSED BROKER VALIDATION"
                : "TRADE BLOCKED"}
            </strong>

            <span>
              {preview.message}
            </span>
          </div>
        </div>
      )}

      {preview && (
        <div className="trade-review-preview-grid">
          <PreviewMetric
            label="Broker symbol"
            value={preview.broker_symbol}
          />

          <PreviewMetric
            label="Live execution price"
            value={formatNumber(
              preview.execution_price,
            )}
          />

          <PreviewMetric
            label="Signal deviation"
            value={formatPercent(
              preview.signal_price_deviation_percent,
            )}
          />

          <PreviewMetric
            label="Spread"
            value={formatNumber(
              preview.market?.spread,
            )}
          />

          <PreviewMetric
            label="Margin required"
            value={formatNumber(
              preview.margin?.required,
            )}
          />

          <PreviewMetric
            label="Free margin"
            value={formatNumber(
              preview.margin?.free,
            )}
          />

          <PreviewMetric
            label="Estimated risk"
            value={formatNumber(
              preview.risk?.amount,
            )}
          />

          <PreviewMetric
            label="AI management"
            value={
              form.aiManagementEnabled
                ? "ON"
                : "OFF"
            }
          />
        </div>
      )}

      {preview?.approved && !intent && (
        <div className="trade-review-intent-section">
          <div className="trade-review-intent-header">
            <div>
              <span>Step 2</span>

              <strong>
                Create protected trade intent
              </strong>
            </div>

            <ShieldCheck size={21} />
          </div>

          <p>
            This records the exact manual setup and
            AI-management preference. It does not send
            an MT5 order.
          </p>

          <button
            type="button"
            className="trade-review-preview-button"
            onClick={createIntent}
            disabled={intentLoading}
          >
            {intentLoading ? (
              <>
                <LoaderCircle
                  size={18}
                  className="spin"
                />
                Creating intent...
              </>
            ) : (
              <>
                <ShieldCheck size={18} />
                Create trade intent
              </>
            )}
          </button>
        </div>
      )}

      {intent && !confirmation && (
        <div className="trade-confirmation-card">
          <div className="trade-confirmation-header">
            <div>
              <span>Final safety gate</span>

              <h3>
                Confirm this manual trade
              </h3>
            </div>

            <ShieldCheck size={24} />
          </div>

          <div className="trade-confirmation-warning">
            <AlertTriangle size={19} />

            <div>
              <strong>
                This is the final execution action.
              </strong>

              <span>
                The server re-checks ownership, expiry,
                broker conditions, risk and MT5 state
                before sending the order.
              </span>
            </div>
          </div>

          <div className="trade-review-preview-grid">
            <PreviewMetric
              label="Intent"
              value={`#${
                intent.intent_id ??
                intent.id
              }`}
            />

            <PreviewMetric
              label="Direction"
              value={form.direction.toUpperCase()}
            />

            <PreviewMetric
              label="Volume"
              value={form.volume}
            />

            <PreviewMetric
              label="Entry"
              value={form.entry}
            />

            <PreviewMetric
              label="Stop loss"
              value={form.stopLoss}
            />

            <PreviewMetric
              label="Take profit"
              value={form.takeProfit}
            />

            <PreviewMetric
              label="AI management"
              value={
                form.aiManagementEnabled
                  ? "ON"
                  : "OFF"
              }
            />

            <PreviewMetric
              label="Expires"
              value={formatExpiry(
                intent.expires_at,
              )}
            />
          </div>

          <button
            type="button"
            className="trade-review-preview-button"
            onClick={confirmTrade}
            disabled={confirmationLoading}
          >
            {confirmationLoading ? (
              <>
                <LoaderCircle
                  size={18}
                  className="spin"
                />
                Confirming with MT5...
              </>
            ) : (
              <>
                <ShieldCheck size={18} />
                Confirm & Execute Manual Trade
              </>
            )}
          </button>
        </div>
      )}

      {confirmation && (
        <div
          className={`trade-review-result ${
            confirmation.execution_status ===
            "executed"
              ? "approved"
              : "blocked"
          }`}
          style={{ marginTop: 18 }}
        >
          {confirmation.execution_status ===
          "executed" ? (
            <CheckCircle2 size={21} />
          ) : (
            <AlertTriangle size={21} />
          )}

          <div>
            <strong>
              {formatConfirmationStatus(
                confirmation,
              )}
            </strong>

            <span>
              {confirmation.message ||
                "The server returned the final trade state."}
            </span>
          </div>
        </div>
      )}

      {(intent || confirmation) && (
        <button
          type="button"
          className="trading-refresh-button"
          onClick={resetTrade}
          style={{ marginTop: 16 }}
        >
          Start another manual trade
        </button>
      )}
    </section>
  );
}

function PreviewMetric({ label, value }) {
  return (
    <div className="trade-review-preview-metric">
      <span>{label}</span>
      <strong>{value ?? "--"}</strong>
    </div>
  );
}

function formatNumber(value) {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return "--";
  }

  const parsed = Number(value);

  if (!Number.isFinite(parsed)) {
    return "--";
  }

  return parsed.toLocaleString(
    undefined,
    {
      maximumFractionDigits: 6,
    },
  );
}

function formatPercent(value) {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return "--";
  }

  const parsed = Number(value);

  if (!Number.isFinite(parsed)) {
    return "--";
  }

  return `${parsed.toFixed(4)}%`;
}

function formatExpiry(value) {
  if (!value) {
    return "--";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "--";
  }

  return date.toLocaleString();
}

function formatConfirmationStatus(
  confirmation,
) {
  if (
    confirmation.execution_status ===
    "executed"
  ) {
    return "MANUAL TRADE EXECUTED";
  }

  if (
    confirmation.execution_status ===
    "execution_reconciliation_required"
  ) {
    return "EXECUTION SENT — RECONCILIATION REQUIRED";
  }

  if (
    confirmation.execution_status ===
    "rejected"
  ) {
    return "TRADE REJECTED";
  }

  return String(
    confirmation.execution_status ||
      "trade_state_received",
  )
    .replaceAll("_", " ")
    .toUpperCase();
}

export default ManualTradeSetup;
