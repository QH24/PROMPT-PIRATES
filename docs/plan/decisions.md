# Stock Mover: Decisions

Verified against: repo `main` @ `aa3e6cf`; data `~/Downloads/manyavar-vch3-data/csv/` (as of 2026-10-31). `D/` below means that csv folder.

## 1. Context
- Intended: one command produces a daily, rule-clean, explained list of WH->store, store->store and pull-back moves, plus a page where a merchandiser can approve it in 10 minutes.
- Existing: repo holds only `index.html` (lip-balm quiz, 74 lines, commit `aa3e6cf`), `README.md`, `.gitignore` (`.env`, `__pycache__/`, `.venv/`). No engine code exists. pandas is **not installed** on the system Python (checked: `ModuleNotFoundError`).
- Brief: `briefs/B_Stock_Mover_brief.pdf` p2. Judged on: hidden problems found, spot-checked numbers, no rule broken, runs on its own, "zero sales is not always slow".

## 2. Stakeholders
- Merchandiser (the one role demoed end to end): approves / skips / edits moves.
- Warehouse (WH-KOL): receives the pick list.
- Judges (Manyavar): spot-check numbers and rules.

## 3. User actions
- Merchandiser can: approve all routine moves in one click; approve / skip (with reason) / edit qty per row; filter by store; export approved CSV, pick list CSV, approvals JSON.
- Operator can: run `python engine/run.py --date YYYY-MM-DD`; run the validator alone, with or without an injected bad move.

## 4. Permissions
- No auth (cut). Single role. Page is local/static.

## 5. Limitations (cut, do not build)
- Sarvam voice (at most a pre-recorded 20 s clip, outside the build). Never read `.env`.
- Multi-role "view as"; real auth; messaging; backtests; feedback loops; auto-reorder; manufacturer alerts; perishables.
- No LLM anywhere in the decision path or in reason text.
- No server: status persists in browser `localStorage` + exported `approvals.json` (see D9).
- Seasonal forecasting model (see A3).

## 6. Edge cases (these are the test surface)
- `D/stock_snapshot.csv:1392` KNP-03 SHW-02-L on_hand **300** vs `D/stock_weekly.csv:58337` closing 0, days_in_stock 0 on the same date -> suspected keying error worth Rs 83,09,700 at MRP; it alone causes KNP-03 "208% of capacity" (520/250; 220/250 without it). Do not pull back; hold for physical count.
- `D/stock_snapshot.csv:2368` MYS-02 KUR-02-M on_hand **-4** vs weekly closing 3 -> data error; quarantine.
- MZF-01 (`D/stores.csv:13`) at 128/350 and Mojari 5 < min 8 -> real under-stock.
- BLR-05 opened 2026-10-10 (`D/stores.csv:19`), first bill 2026-10-10, Sherwani 2 < min 5 -> thin history; every move to it is an exception.
- Zero sales with low `days_in_stock` = unavailable, not slow -> never pulled back / donated on that basis.
- 55 units in transit, all arriving 2026-11-01/02 -> count as arriving; never resent.
- Calendar: Diwali 2026-11-08 (all 3 states), Chhath 2026-11-15 (Bihar), wedding dates 2026-11-20..30. South WH lead is 6 days.
- Two moves from the same donor that each pass alone and fail together.

## 7. Failure handling
- Missing/renamed CSV column -> `run.py` exits non-zero naming the file+column; no partial output written.
- Validator finds a violation -> `run.py` still writes the file but `validator.violations > 0`; page badge turns red; exit code 2.
- Engine crash on demo day -> page loads `demo/moves.js` (pre-baked, committed).
- Browser storage cleared -> statuses reset to Proposed; approvals.json export is the durable copy.

## 8. Dependencies
- Python 3 + pandas (new `requirements.txt`; installed into `.venv`). Validator: stdlib only.
- Google Fonts (Playfair Display, DM Sans) at page load; page must still work offline with fallback fonts.

## 9. Non-functional
- NFR-1: `run.py` end to end (load 2.6 lakh bill lines -> moves + validation) <= 60 s wall clock on the demo laptop — verify: `time python engine/run.py --date 2026-10-31`.
- NFR-2: page first render <= 2 s from `file://` with full moves.js — verify: open with DevTools Performance, once.
- NFR-3: a teammate who has not seen the list approves it in <= 10 min — verify: timed dry run in hour 8.
- NFR-4: validator independence — `validator/` imports nothing from `engine/` and no pandas — verify: grep (TC-I1).

## Decision log
- D1 (given, user): Python 3 + pandas engine in `engine/`, entry `engine/run.py`; deterministic; no LLM decisions — rules out: LLM-ranked moves, notebooks as the product.
- D2 (given, user): UI = one static `index.html` + vanilla JS — rules out: React, bundlers, build step.
- D3 (given, user): config in `config/`, CSVs copied to `data/` (git-ignored), output in `out/` — rules out: reading from `~/Downloads` at runtime.
- D4 (given, council): reasons are template strings filled from numbers in the move's own `evidence` — rules out: LLM prose, free text not traceable to a number.
- D5 (given, council): independent validator, stdlib `csv` only, written from `D/rules.csv` text, own constants, no import of engine code — rules out: validator reusing engine helpers or config.
- D6 (2026-11-21, architect): quarantine rule = snapshot `on_hand < 0` OR snapshot `on_hand` != `stock_weekly.closing_on_hand` for `week_ending == as_of`. Catches exactly 2 rows today. Quarantined (location, sku) never sends or receives — rules out: hand-coding the two SKUs; "fixing" the number.
- D7 (2026-11-21, architect): velocity = units sold in last 28 days / days that SKU was in stock in those 28 days (from `stock_weekly.days_in_stock`, 4 weeks ending as_of) — rules out: raw 91-day average (dilutes October festive rate, punishes stock-outs). Consequence: velocity at stock-out SKUs rises, so needs grow; first-pass counts (534/373/1,599) will change and must be re-derived, not quoted.
- D8 (2026-11-21, architect): one move = one (from, to, sku); never split to dodge Rs 1 lakh; Rs 1 lakh is per move line at MRP, `>` 1,00,000 needs approval — rules out: per-batch threshold, splitting.
- D9 (2026-11-21, architect): status lives in `localStorage` + "Export approvals" download; `run.py` reads `state/approvals.json` if present to drop Skipped keys — rules out: a Flask/Node server for writes.
- D10 (2026-11-21, architect): `run.py` writes `out/moves.js` (`window.MOVES = {...}`) next to `moves.json` so `index.html` opens by double-click, no server, no fetch/CORS — rules out: `fetch('out/moves.json')` over `file://`.
- D11 (2026-11-21, architect): old quiz `index.html` is removed with `git rm` (recoverable from `aa3e6cf`) and replaced — rules out: keeping two pages at root.
- D12 (2026-11-21, architect): engine uses a stricter internal donor floor (45 days) than the rule (30); validator checks the rule (30) — rules out: engine and validator sharing one number, which would hide a drift.

## Options considered
- A (chosen): pandas engine with a mutable ledger; every candidate move checked against the ledger in priority order; then an independent stdlib validator over the final list. Wins: combination-safe by construction and proven by a second program.
- B (rejected): LP/optimizer (pulp/OR-tools) — new dependency, opaque "why", no time to debug infeasibility.
- C (rejected): per-move checks only (no ledger) — fails the two-moves-one-donor case.
- D (rejected): validator imports engine's `metrics.py` — shares bugs; not independent.

## Assumptions (defaults picked; shown on the page)
- A1: "Today" = `--date`; stock = 31 Oct snapshot rolled forward: in-transit with `arrives_on <= date` becomes on_hand; `warehouse_inbound` with `expected_date <= date` added to WH. Sales after 31 Oct unknown.
- A2: Rs 1,00,000 threshold is per move line (qty x MRP), not per batch.
- A3: No seasonal multiplier. The 28-day window already holds the October festive rate (Oct 7,264 vs Sep 3,473 units); Nov festivals/weddings only raise priority and appear in the reason.
- A4: New store BLR-05 and any SKU with < 14 in-stock days in the window: velocity flagged `THIN_DATA`; moves to it are exceptions; never a donor or pull-back on zero sales.
- A5: Donor-cover rule is applied at style level (rule text: "for that style", `D/rules.csv:6`); engine also checks SKU level.
- A6: Min display is a donor-side rule at category level; Safa+Mala+Stole summed into "Accessories (Safa/Mala/Stole)" (README note 9).
- A7: Capacity counts on_hand + in_transit, negatives clamped to 0, quarantined units included as reported (conservative: KNP-03 receives nothing).
- A8: Pull-back lead time = WH->store lead for that store's zone (no route given).
- A9: Packaging SKUs (`PKG-BAG`, `PKG-COVER`, `PKG-BOX`) excluded everywhere.
- A10: Store->store moves across zones (7 days) allowed but always an exception.

## Open
- None blocking. Q1 (owner: team, decide by hour 7): show KNP-03 SHW-02-L also as a conditional "if count confirms 300, pull back 270, needs approval" row? Default: no, finding only.
