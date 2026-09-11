from pathlib import Path

path = Path("src/App.jsx")
text = path.read_text(encoding="utf-8-sig")

nav_marker = '''  {
    to: "/positions",
    label: "Positions",
    icon: BriefcaseBusiness,
  },'''

nav_insert = '''  {
    to: "/trading",
    label: "Trading",
    icon: TrendingUp,
  },
''' + nav_marker

route_marker = '''            <Route
              path="/positions"
              element={<Positions />}
            />'''

route_insert = '''            <Route
              path="/trading"
              element={<TradingPage />}
            />

''' + route_marker

if 'to: "/trading"' not in text:
    if nav_marker not in text:
        raise SystemExit("ERROR: Positions navigation marker not found.")
    text = text.replace(nav_marker, nav_insert, 1)
    print("SUCCESS: Trading navigation added.")
else:
    print("INFO: Trading navigation already exists.")

if 'path="/trading"' not in text:
    if route_marker not in text:
        raise SystemExit("ERROR: Positions route marker not found.")
    text = text.replace(route_marker, route_insert, 1)
    print("SUCCESS: Trading route added.")
else:
    print("INFO: Trading route already exists.")

path.write_text(text, encoding="utf-8")
print("DONE: App.jsx updated.")
