# Stock Mover: LLD

Verified against: repo `main` @ `aa3e6cf`; data as of 2026-10-31. `D/` = `~/Downloads/manyavar-vch3-data/csv/`. Decision IDs (D#, A#) are in `decisions.md`.

## Goal / acceptance
- `python engine/run.py --date 2026-10-31` writes `out/moves-2026-10-31.json`, `out/moves.json`, `out/moves.js`, exits 0, in <= 60 s.
- Validator reports `0 violations` on that file and rejects every file in `validator/bad/`.
- `index.html` (double-click) shows numbers, findings, grouped moves, blocked list, validator badge, assumptions; exports approved CSV + pick list.

## Constraints found in data
- IDs are text: read every CSV with `dtype=str`, cast numerics explicitly (README "Things people get wrong" 13).
- `D/min_display.csv` uses "Accessories (Safa/Mala/Stole)"; `items.category` has Safa/Mala/Stole separately (README 9).
- `D/lead_times.csv` routes are sentences: WH->East 3, North 4, South 6; store->store same city 2, same zone 4, different zone 7. Hard-map by zone/city; do not parse sentences.
- `stores.zone`: North=UP, East=Bihar, South=Karnataka. WH-KOL is not in `stores` (README 6).
- `stock_weekly` weeks end Saturday; 12 weeks 2026-08-15..2026-10-31; `days_in_stock` 0-7.
- `flagship_protected`: 20 styles each for LKO-01, PAT-01, BLR-01, BLR-02 (all S++). Example `D/flagship_protected.csv:2` LKO-01 KUR-02.
- `oldest_stock_received_on` blank on 28 rows, all with on_hand 0 -> not an error.
- In transit: 44 rows / 55 units, arrive 2026-11-01 (40 rows) or 11-02 (4).

## Module layout (one owner per file)
```
engine/run.py        CLI, wiring, writes outputs, calls validator via subprocess
engine/load.py       read data/*.csv, roll forward to --date, quarantine
engine/metrics.py    velocity, cover, age, per (loc, sku) frame
engine/plan.py       needs, ledger, candidate checks, moves, blocked
engine/report.py     reason templates, findings, self-audit, diff, CSV/JSON/JS writers
validator/validate.py  stdlib only; never imports engine/ or pandas
validator/bad/*.json   adversarial move files (one rule each)
config/rules.json    engine thresholds (validator does NOT read this)
index.html           UI (root; replaces quiz)
demo/moves.js        pre-baked fallback (committed)
data/ out/ state/    git-ignored
requirements.txt     pandas
```

## config/rules.json (engine only)
```json
{"velocity_window_days":28, "thin_data_days":14, "under_cover_days":14, "target_cover_days":30,
 "donor_rule_days":30, "donor_keep_days":45, "donor_min_cover_days":60,
 "pullback_cover_days":120, "pullback_age_days":120, "pullback_keep_days":60,
 "approval_mrp_rs":100000, "festival_lookahead_days":21}
```

## Formulas (both programs implement these independently)
- `in_stock_days_28(loc,sku)` = sum of `days_in_stock` over the 4 `stock_weekly` rows with `week_ending` in (as_of-21 .. as_of) = 2026-10-10, 10-17, 10-24, 10-31.
- `sold_28(loc,sku)` = sum `bill_lines.qty` joined to `bills` where `store_id=loc` and `bill_date` in (as_of-27 .. as_of) = 2026-10-04..10-31.
- `v(loc,sku)` units/day = `sold_28 / max(in_stock_days_28, 7)`. If `in_stock_days_28 < 14` -> flag `THIN_DATA`.
- `v_style(loc,style)` = sum of `v` over sizes.
- `avail(loc,sku)` = `max(on_hand,0) + in_transit` (after roll-forward A1).
- `cover_days` = `avail / v`; `v == 0` -> `inf` (JSON: `null`, UI shows "no sales").
- `age_days` = `date - oldest_stock_received_on`.
- Need (receiver): if `v > 0` and `cover_days < under_cover_days`: `need = ceil(v * (target_cover_days + lead_WH(loc))) - avail`, skip if `need <= 0`.
- Donor give-max (store->store), all must hold, take min:
  - SKU: `on_hand - ceil(v_d * donor_keep_days)` and donor `cover_days >= donor_min_cover_days`
  - Style: `style_on_hand_after / v_style >= donor_rule_days` (rule, A5)
  - Category: `cat_on_hand_after >= min_display[tier][cat]` (A6)
  - Not flagship-protected; not quarantined; not THIN_DATA with `sold_28 == 0`
- Receiver cap: `cap_room = stock_capacity_units - sum(avail over store)` from the ledger; `qty <= cap_room`.
- Pull-back: `age_days >= 120` and (`cover_days >= 120` or (`sold_28 == 0` and `in_stock_days_28 >= 21`)); `qty = on_hand - ceil(v * pullback_keep_days)`, bounded by min display. `sold_28 == 0` and `in_stock_days_28 < 14` -> `not_slow` list, untouched.

## Seams (signatures)
```python
# load.py
def load_all(data_dir: Path, run_date: date) -> Inputs
# Inputs: NamedTuple(stores: DataFrame, items: DataFrame, snap: DataFrame, weekly: DataFrame,
#   sales28: DataFrame[store_id, sku_id, sold_28], inbound: DataFrame, calendar: DataFrame,
#   min_display: dict[(tier, cat)] -> int, protected: set[(store_id, style_id)],
#   quarantine: DataFrame[location_id, sku_id, reason, on_hand, weekly_close], as_of: date)
# Raises SystemExit(1) with "file:column missing" on schema mismatch. Drops is_packaging==1.

# metrics.py
def build_position(inp: Inputs, cfg: dict) -> DataFrame
# one row per (location_id, sku_id): on_hand:int, in_transit:int, avail:int, sold_28:int,
#   in_stock_days_28:int, v:float, cover_days:float, age_days:int|NaN, thin:bool,
#   quarantined:bool, style_id, category_md (min-display category), mrp:int

def lead_days(src: str, dst: str, stores: DataFrame) -> int   # WH-KOL allowed as src or dst (A8)

# plan.py
class Ledger:                       # the ONLY mutable stock state
    def __init__(self, pos: DataFrame, stores: DataFrame): ...
    def apply(self, src: str, dst: str, sku: str, qty: int) -> None
    def on_hand(self, loc, sku) -> int; def style_on_hand(self, loc, style) -> int
    def cat_on_hand(self, loc, cat) -> int; def store_total(self, loc) -> int
def check(ledger, pos, cfg, src, dst, sku, qty) -> tuple[int, list[str]]
# returns (max allowed qty <= qty, list of rule codes that cut it). Called for EVERY candidate.
def plan(inp: Inputs, pos: DataFrame, cfg: dict, skipped: set[str]) -> tuple[list[Move], list[Blocked]]

# report.py
def reason(m: Move) -> str
def findings(inp, pos, moves, blocked) -> list[dict]
def self_audit(inp, pos, moves) -> list[dict]
def diff(prev_path: Path | None, moves: list[Move]) -> dict
def write_all(out_dir: Path, run_date: date, payload: dict) -> None  # json, latest json, js, approved/pick CSV headers

# validator/validate.py  (stdlib)
def main(argv) -> int   # --moves PATH --data DIR [--inject PATH] [--out PATH]; exit 0 clean, 2 violations
```
Failure: `run.py` writes outputs to a temp name and `os.replace`s at the end -> no partial `moves.json`.

## Plan algorithm (deterministic order)
1. `needs` sorted by: `avail == 0` desc, `cover_days` asc, days to next festival/wedding in store's state asc, tier (S++,S+,A,B), store_id, sku_id.
2. For each need, candidate sources sorted by `lead_days` asc, then `WH-KOL` first, then larger donor excess, then store_id. For each: `ok, cut = check(...)`; if `ok > 0` emit move and `ledger.apply`; record every `cut` code against a source that had stock as a `Blocked` row (dedupe by key). Stop when need met.
3. Pull-backs: after step 2, for each pull-back candidate, first try to place into a remaining need elsewhere (already done in 2), else `PULL_BACK` to WH-KOL via `check`.
4. Skip keys in `state/approvals.json` with status `Skipped` (D9) -> listed in `blocked` as `SKIPPED_BY_USER`.
5. Unmet need after all sources -> `Blocked{rule: NO_SOURCE}` (shows "WH and donors empty").

Combination safety: every `check` reads the Ledger, which already reflects all earlier moves. Two moves from one donor are judged on the donor's post-first-move stock.

## moves.json contract (`schema: 1`)
```
run:       {date, as_of, generated_at, git_sha, inputs: {file: row_count}}
summary:   {moves, units, value_mrp, routine, exceptions, blocked,
            by_type: {WH_TO_STORE, STORE_TO_STORE, PULL_BACK}}
validator: {checked, violations, rules: ["R1".."R8"], details: [{move_id, rule, detail}]}
moves[]:   {move_id: "<from>><to>><sku_id>",      # stable across days; used for diff + skip
            type: "WH_TO_STORE"|"STORE_TO_STORE"|"PULL_BACK",
            from, to, sku_id, style_id, style_name, category, size,
            qty:int, mrp:int, value_mrp:int, lead_days:int, dispatch_on, arrives_on,
            needs_approval:bool, warnings:[ "THIN_DATA"|"NEW_STORE"|"CROSS_ZONE"|"BELOW_MIN_DISPLAY_RECEIVER" ],
            routine:bool,                          # !needs_approval && warnings==[]
            reason:str,                            # template, <= 120 chars
            evidence: {to_on_hand, to_in_transit, to_v_week, to_cover_before, to_cover_after,
                       from_on_hand, from_cover_before, from_cover_after, sold_28,
                       in_stock_days_28, age_days, event: {name, date, days_away}|null},
            finding_ids:[str], status:"Proposed"}
blocked[]: {from, to, sku_id, qty_wanted, rule: "FLAGSHIP"|"DONOR_COVER"|"MIN_DISPLAY"|"CAPACITY"|
            "IN_TRANSIT"|"DATA_SUSPECT"|"NO_SOURCE"|"SKIPPED_BY_USER", detail}
findings[]:{id, title, kind: "DATA_ERROR"|"REAL_PROBLEM"|"CONTEXT", evidence, value_rs, move_ids, action}
not_slow[]:{store_id, sku_id, on_hand, in_stock_days_28, note}
self_audit[]: {label, value, formula}
assumptions[]: str   # copied from decisions.md A1-A10
diff:      {vs: filename|null, added:[move_id], removed:[move_id], qty_changed:[{move_id, was, now}]}
```
`out/moves.js` = `window.MOVES = <same JSON>;`. Status values (UI only): `Proposed, Approved, Skipped, Dispatched, Received`.

## Reason templates (report.py, numbers only from `evidence`)
- WH_TO_STORE: `Send {qty} from WH: {to_on_hand} on hand{ +it in transit}, sells {to_v_week}/wk, cover {before}d -> {after}d, arrives {arrives_on}{, Diwali in 8 days}`
- STORE_TO_STORE: `Move {qty} {from}->{to}: {from} keeps {from_cover_after}d cover, {to} has {to_cover_before}d and sells {to_v_week}/wk, {lead}d`
- PULL_BACK: `Pull back {qty} to WH: {age}d old, sold {sold_28} in 28d, cover {from_cover_before}d, no store needs it`

## Findings (seeded; engine computes values)
| id | kind | what | link |
|---|---|---|---|
| F1 | DATA_ERROR | KNP-03 SHW-02-L 300 vs weekly 0 (`D/stock_snapshot.csv:1392`, `D/stock_weekly.csv:58337`); Rs 83,09,700; explains KNP-03 208% | blocked DATA_SUSPECT, action "count" |
| F2 | DATA_ERROR | MYS-02 KUR-02-M on_hand -4 vs weekly 3 (`:2368`, `:59848`) | blocked DATA_SUSPECT |
| F3 | REAL_PROBLEM | MZF-01 128/350, Mojari 5 < 8 | moves to MZF-01 |
| F4 | REAL_PROBLEM | sell-with-no-stock pairs (count, lost Rs/wk = sum v*7*mrp) | WH/S2S moves |
| F5 | REAL_PROBLEM | ageing > 120 d (units, Rs) | PULL_BACK / S2S |
| F6 | CONTEXT | zero-sales-but-unavailable ("would have been flagged slow, correctly not touched") | `not_slow` |
| F7 | CONTEXT | BLR-05 new (2026-10-10), Sherwani 2 < 5 | moves with NEW_STORE |
| F8 | CONTEXT | Oct 7,264 vs Sep 3,473 units; Diwali 11-08, Chhath 11-15, weddings 11-20..30 | reason text |
| F9 | CONTEXT | 55 units in transit counted; 0 resent | validator R4 |

## Independent validator (validator/validate.py)
Stdlib `csv`, `json`, `math`, `datetime` only. Reads `data/*.csv` itself; own constants typed from `D/rules.csv` (`30`, `100000`) and own route table from `D/lead_times.csv`. Builds end state by summing all moves per (loc,sku), (loc,style), (loc,category), (loc) — i.e. checks the list **in combination**, never move by move.
| R | Check (violation if false) |
|---|---|
| R1 min display | every donor (store) category end on_hand >= min_display[tier][cat], Safa/Mala/Stole summed |
| R2 capacity | every receiving store: sum(on_hand>=0 + in_transit) + in - out <= capacity |
| R3 flagship | no move with `from` S++ and `(from, style)` in flagship_protected |
| R4 in-transit | no move to (store,sku) whose `on_hand + in_transit >= ceil(v*30)` before the move; and `qty <= ceil(v*37) - (on_hand+in_transit)` |
| R5 donor cover | store->store donor: style end on_hand / v_style >= 30 (v_style 0 -> pass) |
| R6 approval | `qty*mrp > 100000` => `needs_approval == true` |
| R7 lead time | `lead_days` == route table; `arrives_on == dispatch_on + lead_days` |
| R8 conservation | qty int > 0; from != to; unique move_id; sum out per (loc,sku) <= on_hand (WH incl. inbound <= date); no packaging, unknown or quarantined (loc,sku); network units before == after |
Output: table to stdout, JSON to `--out`; exit 2 on any violation. `--inject f.json` appends those moves before checking (demo).

## Rollout
- Day run: `python engine/run.py --date 2026-10-31`, then `--date 2026-11-02` to show a diff (in-transit lands, inbound arrives). Optional `.github/workflows/daily.yml` cron — only if hour 8 has slack.
- Rollback: `demo/moves.js` committed; `index.html` loads `out/moves.js`, falls back to `demo/moves.js` via `<script onerror>`.

## Design tokens (eyeballed from a blurred screenshot; NOT exact)
```css
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;700&family=DM+Sans:wght@400;500;700&display=swap');
:root{
  --bg:#FAF7F0; --surface:#FFFDF8; --card:#FFFFFF; --tint:#F7F1E6;
  --maroon:#7F1D2D; --maroon-2:#8B2035; --gold:#A67C37;
  --text:#3B302A; --muted:#7A6C62; --line:#E8DFD0;
  --ok:#2E7D4F; --warn:#B7791F; --bad:#B42318;
  --r-card:24px; --r-btn:14px; --r-chip:999px;
  --shadow:0 6px 24px rgba(60,40,20,.08);
  --serif:'Playfair Display',Georgia,serif; --sans:'DM Sans',system-ui,sans-serif;
  --gutter:16px;
}
.btn{background:linear-gradient(180deg,var(--maroon-2),var(--maroon));color:#fff;border-radius:var(--r-btn)}
.eyebrow{font:500 11px/1 var(--sans);letter-spacing:.18em;text-transform:uppercase;color:var(--gold)}
.card{background:var(--card);border-radius:var(--r-card);box-shadow:var(--shadow);border-left:3px solid var(--gold)}
```
## UI mapping (single column, `max-width:720px`, 16px gutter, mobile first)
| Piece | Visual | Data |
|---|---|---|
| Header | logo mark, divider, "STOCK DESK" small caps, maroon avatar "M" | static |
| Eyebrow row | dot (green if `validator.violations==0` else red), "STORE OPERATIONS", divider, date | `run.date` |
| Greeting | serif "Good morning", one-line subtitle "N moves ready, M need you" | `summary` |
| Top numbers | 4 tiles: moves, units, Rs at MRP, need approval | `summary` |
| Validator badge | card, serif "0 of N moves break 8 rules", R1-R8 chips, "how checked" note | `validator` |
| Findings | alert cards: coloured left bar (maroon REAL_PROBLEM, gold DATA_ERROR, taupe CONTEXT), serif headline, sentence with bold numbers, store chips, "See 12 moves" button (filters list) | `findings` |
| Move list | grouped by destination store; group header with "Approve all routine (n)"; exceptions expanded first, routine collapsed | `moves` |
| Move row | checkbox (pre-ticked if routine), style + size, from->to chip, qty `<input type=number>`, Rs, reason line in muted text, warning chips, Approve / Skip | `moves[i]` |
| Skip modal | white card, gold eyebrow, serif title, tinted note, reason `<select>`, full-width maroon "Skip move ->", "Not now" link | |
| Blocked list | `<details>` per rule code with count; rows: from->to, sku, rule, detail | `blocked` |
| Not-slow | `<details>` "Would have been flagged slow, correctly not touched (n)" | `not_slow` |
| Assumptions | tinted box | `assumptions` |
| Footer actions | Export approved CSV, Pick list CSV, Approvals JSON; store filter `<select>` | |
Qty edit: clamp to `1..original qty` (raising qty could break a rule the validator checked).

## Drift log
- Prompt's first-pass "~534 under 14 d / ~373 over 120 d / ~1,599 zero-sales" used a 91-day velocity; D7 uses 28 days over in-stock days -> numbers will differ. Re-derive; do not pitch the old ones.
- Prompt says KNP-03 holds 520 vs 250: true as reported, but 300 of it is one suspect row (F1).
- Prompt lists "3 packaging SKUs": confirmed `PKG-BAG, PKG-COVER, PKG-BOX`; none appear in `stock_snapshot`.

## Open questions
- Q1 (non-blocking): conditional pull-back row for F1 — recommend no (finding only, keeps "the list that can't lie").

## Eval (round 1)
| Case | Result | Evidence |
|---|---|---|
| E1 reuse | PASS | no existing code; pandas/stdlib only |
| E2 traces | PASS | every module maps to council points 1-8 |
| E3 single-use layers | PASS | 5 engine files, no classes except Ledger (shared state, used by check+plan) |
| E5 branching | PASS | one `check()` for all move types |
| E6 source of truth | PASS | thresholds in config/rules.json; rules from D/ CSVs |
| E7 traced values | PASS | IDs `dtype=str`; qty int; dates ISO strings in JSON |
| E9 common shape | PASS | single moves.json contract |
| E12 asked vs verified | PASS | data claims cite CSV lines; prompt figures logged as drift |
| E13 lean docs | PASS | reasoning in decisions.md only |
| E14 NFR->NFT | PASS | NFR-1..4 -> NFT-1..4 |
| E15 side effects | PASS | validator subprocess failure marks badge red, never blocks output |
| E16 validate then write | PASS | temp file + os.replace |
| E19 repeatable | PASS | deterministic sort keys; same input -> byte-identical moves (TC-D1) |
| E4, E8, E10, E11, E17, E18, E20 | N/A | no layered backend, no DB/SQL, no tenants, no external callers |
