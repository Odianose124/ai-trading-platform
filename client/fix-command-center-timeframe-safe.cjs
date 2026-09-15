const fs = require("fs");
const path = require("path");

const file = path.join(__dirname, "src", "App.jsx");

let source = fs.readFileSync(file, "utf8");

const original = source;

// 1. Add tradingSettings state to CommandCenter
const stateAnchor = `  const [positionSummary, setPositionSummary] = useState(null);
  const [loading, setLoading] = useState(true);`;

const stateReplacement = `  const [positionSummary, setPositionSummary] = useState(null);
  const [tradingSettings, setTradingSettings] = useState(null);
  const [loading, setLoading] = useState(true);`;

if (!source.includes(stateAnchor)) {
  throw new Error(
    "Could not find the CommandCenter state block."
  );
}

source = source.replace(stateAnchor, stateReplacement);

// 2. Add settings request to Promise.all
const promiseAnchor = `          positionsResponse,
        ] = await Promise.all([
          api.get(
            "/api/mt5/market-data/ticks",
          ),`;

const promiseReplacement = `          positionsResponse,
          settingsResponse,
        ] = await Promise.all([
          api.get(
            "/api/mt5/market-data/ticks",
          ),`;

if (!source.includes(promiseAnchor)) {
  throw new Error(
    "Could not find the CommandCenter Promise.all block."
  );
}

source = source.replace(
  promiseAnchor,
  promiseReplacement
);

// 3. Add settings API call before the Promise.all closes
const positionsRequest = `          api.get(
            "/api/mt5/positions/summary",
          ),
        ]);`;

const positionsReplacement = `          api.get(
            "/api/mt5/positions/summary",
          ),

          api.get(
            "/api/settings",
          ),
        ]);`;

if (!source.includes(positionsRequest)) {
  throw new Error(
    "Could not find the CommandCenter positions request."
  );
}

source = source.replace(
  positionsRequest,
  positionsReplacement
);

// 4. Store settings response
const stateSetAnchor = `        setAccountStatus(accountResponse.data);
        setPositionSummary(positionsResponse.data);`;

const stateSetReplacement = `        setAccountStatus(accountResponse.data);
        setPositionSummary(positionsResponse.data);
        setTradingSettings(settingsResponse.data);`;

if (!source.includes(stateSetAnchor)) {
  throw new Error(
    "Could not find the CommandCenter state update block."
  );
}

source = source.replace(
  stateSetAnchor,
  stateSetReplacement
);

// 5. Add preferred timeframe calculation before aiBias
const biasAnchor = `  const aiBias =
    analysis?.overall_bias || "neutral";`;

const biasReplacement = `  const preferredTimeframe =
    tradingSettings?.preferred_timeframe || "15m";

  const preferredTimeframeLabel = {
    "1m": "1 Minute",
    "5m": "5 Minutes",
    "15m": "15 Minutes",
    "1h": "1 Hour",
    "4h": "4 Hours",
  }[preferredTimeframe] || preferredTimeframe;

  const aiBias =
    analysis?.overall_bias || "neutral";`;

if (!source.includes(biasAnchor)) {
  throw new Error(
    "Could not find the CommandCenter AI bias block."
  );
}

source = source.replace(
  biasAnchor,
  biasReplacement
);

// 6. Replace hardcoded AI analysis endpoint
const aiEndpoint = `"/api/mt5/market-data/analysis/ai/XAUUSD/15m"`;

if (!source.includes(aiEndpoint)) {
  throw new Error(
    "Could not find the hardcoded AI 15m endpoint."
  );
}

source = source.replace(
  aiEndpoint,
  "`/api/mt5/market-data/analysis/ai/XAUUSD/${preferredTimeframe}`"
);

// 7. Replace hardcoded MTF primary timeframe
const mtfTimeframe = `primary_timeframe: "15m",`;

if (!source.includes(mtfTimeframe)) {
  throw new Error(
    "Could not find the hardcoded MTF timeframe."
  );
}

source = source.replace(
  mtfTimeframe,
  "primary_timeframe: preferredTimeframe,"
);

// 8. Replace Command Center hero label
const heroLabel = `XAUUSD · 15m`;

if (!source.includes(heroLabel)) {
  throw new Error(
    "Could not find the Command Center XAUUSD timeframe label."
  );
}

source = source.replace(
  heroLabel,
  `XAUUSD · {preferredTimeframeLabel}`
);

// 9. Replace Intelligence card label
const intelligenceLabel = `title="15m execution bias"`;

if (!source.includes(intelligenceLabel)) {
  throw new Error(
    "Could not find the 15m execution bias label."
  );
}

source = source.replace(
  intelligenceLabel,
  `title={\`${preferredTimeframeLabel} execution bias\`}`
);

// 10. Replace MTF context label
const mtfLabel = `title="15m execution timeframe"`;

if (!source.includes(mtfLabel)) {
  throw new Error(
    "Could not find the 15m execution timeframe label."
  );
}

source = source.replace(
  mtfLabel,
  `title={\`${preferredTimeframeLabel} execution timeframe\`}`
);

// 11. Safety check
if (source === original) {
  throw new Error(
    "No changes were made."
  );
}

fs.writeFileSync(file, source, "utf8");

console.log(
  "Command Center timeframe integration completed successfully."
);
console.log(
  "The Command Center now uses the saved preferred timeframe."
);