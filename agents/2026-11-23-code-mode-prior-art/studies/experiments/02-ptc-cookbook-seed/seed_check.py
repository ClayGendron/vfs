"""Totals of approved travel+lodging Q3 expenses per engineer from the cookbook's mock API, in one process."""
import importlib.util
import json
import sys

spec = importlib.util.spec_from_file_location("team_expense_api", sys.argv[1])
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
team = json.loads(api.get_team_members("engineering"))
out = {}
for m in team:
    rows = json.loads(api.get_expenses(m["id"], "Q3"))
    out[m["id"]] = (len(rows), round(sum(r["amount"] for r in rows if r["status"] == "approved" and r["category"] in ("travel", "lodging")), 2), len(json.dumps(rows)))
print(json.dumps(out))
