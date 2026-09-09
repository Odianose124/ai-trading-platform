from pathlib import Path

app_path = Path("client/src/App.jsx")

text = app_path.read_text(encoding="utf-8-sig")

# Add MarketsPage import if it does not already exist.
import_line = 'import MarketsPage from "./MarketsPage";'

if import_line not in text:
    anchor = 'import TradeHistoryPage from "./TradeHistoryPage";'

    if anchor not in text:
        raise SystemExit(
            "Could not find the TradeHistoryPage import. "
            "App.jsx was not changed."
        )

    text = text.replace(
        anchor,
        anchor + "\n" + import_line,
        1,
    )

# Replace the existing Markets route.
old_route = """<Route
              path="/markets"
              element={<Markets />}
            />"""

new_route = """<Route
              path="/markets"
              element={<MarketsPage />}
            />"""

if old_route not in text:
    raise SystemExit(
        "Could not find the existing Markets route. "
        "App.jsx was not changed."
    )

text = text.replace(
    old_route,
    new_route,
    1,
)

app_path.write_text(
    text,
    encoding="utf-8",
)

print("Markets page connected successfully.")