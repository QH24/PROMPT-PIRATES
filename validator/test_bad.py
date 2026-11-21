#!/usr/bin/env python3
"""Self-check: the valid fixture exits 0; every validator/bad/A*.json exits 2 naming its rule.
Run from repo root: python3 validator/test_bad.py"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
EXPECT = {"A1": "R3", "A2": "R5", "A3": "R2", "A4": "R4", "A5": "R1", "A6": "R6", "A7": "R7",
          "A8": "R8", "A9": "R8", "A10": "R8", "A11": "R8", "A12": "R8", "A13": "R8", "A14": "R8", "A15": "R8"}


def run(path):
    with tempfile.NamedTemporaryFile(suffix=".json") as out:
        p = subprocess.run([sys.executable, str(HERE / "validate.py"), "--moves", str(path),
                            "--data", str(HERE.parent / "data"), "--out", out.name], capture_output=True, text=True)
        res = json.loads(Path(out.name).read_text()) if p.returncode in (0, 2) else None
    return p.returncode, res


code, res = run(HERE / "fixtures" / "ok-3-moves.json")
assert code == 0, f"ok-3-moves: exit {code} {res and res['details']}"
print(f"ok-3-moves  exit 0  {res['checks']} checks, 0 violations")
failed = 0
for case, rule in EXPECT.items():
    code, res = run(HERE / "bad" / f"{case}.json")
    hit = sorted({x["rule"] for x in res["details"]}) if res else []
    ok = code == 2 and rule in hit
    failed += not ok
    print(f"{case:<4} exit {code}  expect {rule}  got {','.join(hit)}  {'PASS' if ok else 'FAIL'}")
print(f"{len(EXPECT) - failed}/{len(EXPECT)} rejected with the expected rule")
sys.exit(1 if failed else 0)
