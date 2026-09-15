const fs = require("fs");
const path = require("path");

const filePath = path.join(
  __dirname,
  "src",
  "App.jsx",
);

let content = fs.readFileSync(filePath, "utf8");

const oldEffect = `  useEffect(() => {
    let mounted = true;

    async function loadCommandCenter() {
      try {
        setError("");

        const [
          priceResponse,
          analysisResponse,
          mtfResponse,
          accountResponse,
          positionsResponse,
        ] = await Promise.all([
          api.get(
            "/api/mt5/market-data/ticks",
          ),

          api.get(
            "/api/mt5/market-data/analysis/ai/XAUUSD/15m",
            {
              params: {
                limit: 500,
                strength: 2,
                lookback: 20,
                minimum_touches: 2,
              },
            },
          ),

          api.get(
            "/api/mt5/analysis/multi-timeframe/XAUUSD",
            {
              params: {
                primary_timeframe: "15m",
                limit: 500,
                strength: 2,
                lookback: 20,
                minimum_touches: 2,
              },
            },
          ),

          api.get(
            "/api/mt5/status",
          ),

          api.get(
            "/api/mt5/positions/summary",
          ),
        ]);

        if (!mounted) {
          return;
        }

        setPrices(priceResponse.data);
        setAnalysis(analysisResponse.data);
        setMtf(mtfResponse.data);
        setAccountStatus(accountResponse.data);
        setPositionSummary(positionsResponse.data);
      } catch (requestError) {
        if (!mounted) {
          return;
        }

        setError(
          requestError?.response?.data?.detail ||
            "Unable to load live trading intelligence.",
        );
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    loadCommandCenter();

    const interval = window.setInterval(
      loadCommandCenter,
      15000,
    );

    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);`;

const newEffect = `  useEffect(() => {
    let mounted = true;

    async function loadCommandCenter() {
      try {
        setError("");

        const settingsResponse = await api.get(
          "/api/settings",
        );

        const preferredTimeframe =
          settingsResponse?.data?.preferred_timeframe ||
          "15m";

        const [
          priceResponse,
          analysisResponse,
          mtfResponse,
          accountResponse,
          positionsResponse,
        ] = await Promise.all([
          api.get(
            "/api/mt5/market-data/ticks",
          ),

          api.get(
            \`/api/mt5/market-data/analysis/ai/XAUUSD/\${preferredTimeframe}\`,
            {
              params: {
                limit: 500,
                strength: 2,
                lookback: 20,
                minimum_touches: 2,
              },
            },
          ),

          api.get(
            "/api/mt5/analysis/multi-timeframe/XAUUSD",
            {
              params: {
                primary_timeframe: preferredTimeframe,
                limit: 500,
                strength: 2,
                lookback: 20,
                minimum_touches: 2,
              },
            },
          ),

          api.get(
            "/api/mt5/status",
          ),

          api.get(
            "/api/mt5/positions/summary",
          ),
        ]);

        if (!mounted) {
          return;
        }

        setPrices(priceResponse.data);
        setAnalysis(analysisResponse.data);
        setMtf(mtfResponse.data);
        setAccountStatus(accountResponse.data);
        setPositionSummary(positionsResponse.data);
      } catch (requestError) {
        if (!mounted) {
          return;
        }

        setError(
          requestError?.response?.data?.detail ||
            "Unable to load live trading intelligence.",
        );
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    loadCommandCenter();

    const interval = window.setInterval(
      loadCommandCenter,
      15000,
    );

    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);`;

if (!content.includes(oldEffect)) {
  throw new Error(
    "The current CommandCenter useEffect block was not found. No changes were made.",
  );
}

content = content.replace(
  oldEffect,
  newEffect,
);

const oldInstrument = `              <span className="instrument-label">
                XAUUSD · 15m
              </span>`;

const newInstrument = `              <span className="instrument-label">
                XAUUSD · {formatTimeframe(
                  mtf?.execution_timeframe ||
                    mtf?.primary_timeframe ||
                    analysis?.timeframe ||
                    "15m",
                )}
              </span>`;

if (!content.includes(oldInstrument)) {
  throw new Error(
    "The current CommandCenter instrument label was not found. No changes were made.",
  );
}

content = content.replace(
  oldInstrument,
  newInstrument,
);

const oldExecutionBias = `        <InsightCard
          title="15m execution bias"
          value={formatBias(executionBias)}
          description="Directional assessment for the primary execution timeframe."
        />`;

const newExecutionBias = `        <InsightCard
          title={\`\${formatTimeframe(
            mtf?.execution_timeframe ||
              mtf?.primary_timeframe ||
              analysis?.timeframe ||
              "15m",
          )} execution bias\`}
          value={formatBias(executionBias)}
          description="Directional assessment for the saved primary execution timeframe."
        />`;

if (!content.includes(oldExecutionBias)) {
  throw new Error(
    "The current execution-bias card was not found. No changes were made.",
  );
}

content = content.replace(
  oldExecutionBias,
  newExecutionBias,
);

const oldMtfExecution = `          <ReasoningBlock
            title="15m execution timeframe"
            value={formatBias(executionBias)}
          />`;

const newMtfExecution = `          <ReasoningBlock
            title={\`\${formatTimeframe(
              mtf?.execution_timeframe ||
                mtf?.primary_timeframe ||
                analysis?.timeframe ||
                "15m",
            )} execution timeframe\`}
            value={formatBias(executionBias)}
          />`;

if (!content.includes(oldMtfExecution)) {
  throw new Error(
    "The current MTF execution timeframe block was not found. No changes were made.",
  );
}

content = content.replace(
  oldMtfExecution,
  newMtfExecution,
);

const marker = `function AccountMetric({`;

const helper = `function formatTimeframe(timeframe) {
  const labels = {
    "1m": "1 Minute",
    "5m": "5 Minutes",
    "15m": "15 Minutes",
    "1h": "1 Hour",
    "4h": "4 Hours",
  };

  return labels[timeframe] || timeframe;
}

`;

if (!content.includes("function formatTimeframe(")) {
  if (!content.includes(marker)) {
    throw new Error(
      "Could not find the helper insertion point. No changes were made.",
    );
  }

  content = content.replace(
    marker,
    helper + marker,
  );
}

fs.writeFileSync(
  filePath,
  content,
  "utf8",
);

console.log(
  "Command Center timeframe integration completed successfully.",
);
console.log(
  "The Command Center now reads preferred_timeframe from /api/settings.",
);