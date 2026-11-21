# Stock Mover: Build spec (~9 h)

Read with `lld.md`. Three parallel lanes after hour 1: **E** engine, **V** validator, **U** UI. Owners blank. Never read, print or copy `.env`.

| Hour | E (engine) | V (validator) | U (UI) |
|---|---|---|---|
| 0:00-0:45 | T1 | T1 | T1 |
| 0:45-1:45 | T2 | T6 | T8 |
| 1:45-3:45 | T3, T4 | T6 | T8 |
| 3:45-5:00 | T5 | T6 finish, start T12 | T9 |
| 5:00-6:30 | T7, then T10 | T12 | T9 |
| 6:30-7:30 | T11 spot-check | T12 run vs real output | T9 polish |
| 7:30-8:15 | T13 fallback + README + day-2 diff | | |
| 8:15-9:00 | T14 pitch rehearsal (all) | | |

### T1 · Scaffold the repo
**Owner:** · **Touches:** `index.html`, `.gitignore`, `requirements.txt`, `config/rules.json`, `data/`
**Do:** `git rm index.html` (quiz stays in `aa3e6cf`). `python3 -m venv .venv && .venv/bin/pip install pandas`; `requirements.txt` = `pandas`. `mkdir -p engine validator/bad config data out state demo`. `cp ~/Downloads/manyavar-vch3-data/csv/*.csv data/`. Append `data/`, `out/`, `state/` to `.gitignore`. Write `config/rules.json` exactly as in lld.
**Do not:** commit `data/` or `.env`; add any other dependency.
**Accept:** `git status` shows no `data/`; `.venv/bin/python -c "import pandas"` ok; 17 CSVs in `data/`.

### T2 · load.py + metrics.py
**Depends on:** T1 · **Touches:** `engine/load.py`, `engine/metrics.py`
**Do:** `load_all` and `build_position` per lld signatures. `dtype=str` on every read. Roll-forward (A1). Quarantine (D6). Drop packaging. Map Safa/Mala/Stole -> min-display category. `lead_days` hard map.
**Do not:** compute velocity over 91 days or divide by calendar days; let a negative on_hand into `avail`.
**Accept:** quarantine frame has exactly 2 rows (KNP-03 SHW-02-L, MYS-02 KUR-02-M). `pos` row count = non-packaging snapshot rows. Total network on_hand printed equals stdlib sum of `stock_snapshot.on_hand` with negatives clamped.
**Verify:** `.venv/bin/python -c "from engine.load import *; ..."` prints the 2 quarantine rows + totals.

### T3 · plan.py: Ledger + check
**Depends on:** T2 · **Touches:** `engine/plan.py`
**Do:** `Ledger.apply(src,dst,sku,q)`: src on_hand -= q; dst in_transit += q (WH dst: on_hand += q). `check()` returns (allowed_qty, cut_codes) applying, in order: DATA_SUSPECT, FLAGSHIP, MIN_DISPLAY, DONOR_COVER (SKU 45 d + style 30 d), CAPACITY, IN_TRANSIT.
**Do not:** read `pos` stock inside `check` — read only the Ledger (combination safety).
**Accept:** assert-based `__main__` self-check: donor with exactly 2 units of give-room; two calls of qty 2 -> first returns 2, after `apply` second returns 0 with `DONOR_COVER`.

### T4 · plan.py: needs, sources, pull-backs
**Depends on:** T3 · **Touches:** `engine/plan.py`
**Do:** lld "Plan algorithm" steps 1-5 with the exact sort keys. Emit `Move` dicts per the contract (minus `reason`). Every cut against a source with stock -> `Blocked`.
**Do not:** split a move to stay under Rs 1 lakh (D8); emit two moves with the same `move_id`; propose to/from quarantined pairs.
**Accept:** two runs on same input give identical move lists. Zero moves out of LKO-01/PAT-01/BLR-01/BLR-02 protected styles. `blocked` contains >= 1 of each: FLAGSHIP, DONOR_COVER, CAPACITY, DATA_SUSPECT.

### T5 · report.py
**Depends on:** T4 · **Touches:** `engine/report.py`
**Do:** reason templates (lld), findings F1-F9 with computed `value_rs` and `move_ids`, `not_slow`, `self_audit` (the 10 rows of test-cases spot-check table, with formula strings), `diff` vs latest earlier `out/moves-*.json`, `write_all` (temp file + `os.replace`), approved/pick CSV columns: `move_id,from,to,sku_id,style_name,size,qty,value_mrp,dispatch_on,arrives_on,reason`.
**Do not:** put any number in a reason that is not in `evidence`.
**Accept:** every reason <= 120 chars; every finding with kind REAL_PROBLEM has >= 1 `move_id` or says why not.

### T6 · validator/validate.py (independent)
**Depends on:** T1 only (write from lld contract + `data/rules.csv`, not from engine code) · **Touches:** `validator/validate.py`
**Do:** R1-R8 per lld table, stdlib only, own constants, end-state aggregation. CLI `--moves --data --inject --out`.
**Do not:** import from `engine/`, `config/`, or pandas; read engine's `evidence` numbers (recompute from CSVs).
**Accept:** on a hand-written 3-move file passes; `grep -rE "engine|pandas|rules.json" validator/` is empty.

### T7 · run.py wiring
**Depends on:** T5, T6 · **Touches:** `engine/run.py`
**Do:** argparse `--date` (required, ISO, >= 2026-10-31), `--data data`, `--out out`. Load `state/approvals.json` if present. Plan -> report -> write -> `subprocess.run([sys.executable, "validator/validate.py", ...])` -> merge result into `validator` block -> rewrite json/js. Exit 0 clean, 2 violations, 1 input error.
**Do not:** swallow validator crash as "0 violations" — crash => `violations: null`, badge "validator did not run".
**Accept:** one command produces `out/moves-2026-10-31.json`, `out/moves.json`, `out/moves.js`; `time` <= 60 s.

### T8 · UI shell on fixture
**Depends on:** lld contract only · **Touches:** `index.html`, `demo/sample.js`
**Do:** hand-write `demo/sample.js` (`window.MOVES=` 6 moves incl. 1 needs_approval, 1 NEW_STORE, 2 blocked, 2 findings). Tokens + layout per lld UI mapping. `<script src="out/moves.js" onerror="load demo/moves.js">`.
**Do not:** add a framework, bundler, or `fetch()`.
**Accept:** page renders the fixture by double-click on a 375 px viewport without horizontal scroll.

### T9 · UI behaviour
**Depends on:** T8 · **Touches:** `index.html`
**Do:** routine pre-ticked; "Approve all routine" per group; Approve/Skip(modal with reason)/qty edit clamped 1..proposed; status in `localStorage["stockmover:"+run.date]`; store filter; exports (approved CSV, pick list = approved WH_TO_STORE grouped by `to`, approvals.json `{move_id: {status, qty, skip_reason}}`); findings "See moves" filters list.
**Do not:** let qty go above proposed; tick exceptions by default.
**Accept:** reload keeps statuses; exported CSV row count = approved count.

### T10 · Real-data run and fix
**Depends on:** T7, T9 · **Touches:** (fixes in owning files only)
**Accept:** validator 0 violations; page shows real file; exceptions <= ~40 (else raise `under_cover_days` or group harder — record in decisions).

### T11 · Spot-check 10 moves in Excel
**Do:** fill test-cases "Spot-check" table and "Hand-verify 10 moves" from `data/*.csv` in Excel (open via Data > From Text, IDs as text).
**Accept:** all 10 numbers match engine to the unit; mismatches fixed or logged.

### T12 · Adversarial set
**Touches:** `validator/bad/*.json` · **Do:** one file per test-cases A1-A15. **Accept:** each exits 2 naming the expected rule.

### T13 · Fallback, diff, README
**Touches:** `demo/moves.js`, `README.md`
**Do:** copy final `out/moves.js` -> `demo/moves.js` and commit. Run `--date 2026-11-02` to show diff. README: setup, one command, validator demo command.
**Accept:** with `out/` deleted the page still renders from `demo/moves.js`.

### T14 · Pitch rehearsal
Demo order: badge -> F1 (the 300 Sherwanis we did not move) -> MZF-01 moves -> blocked list -> inject A1 live -> approve all routine -> export.

## Blocked
- None. (Q1 is a presentation choice; default applies.)
