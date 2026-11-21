# Stock Mover: Test cases

Manual / scripted checks. `V` = `.venv/bin/python validator/validate.py --moves out/moves.json --data data`.

## Functional
- FT-1 Clean run: `python engine/run.py --date 2026-10-31` exits 0; `V` exits 0; badge green.
- FT-2 Determinism (TC-D1): run twice; `diff` of the two `moves` arrays is empty.
- FT-3 Quarantine: no move has (KNP-03, SHW-02-L) or (MYS-02, KUR-02-M) as from/to; both in `blocked` with DATA_SUSPECT; F1 shows Rs 83,09,700.
- FT-4 Flagship: no move from LKO-01/PAT-01/BLR-01/BLR-02 for any style in `flagship_protected.csv`; >= 1 FLAGSHIP blocked row.
- FT-5 In-transit: for each of the 44 in-transit (store, sku) rows, no move is proposed unless cover incl. in-transit < 14 d.
- FT-6 Approval: every move with `value_mrp > 100000` has `needs_approval: true`, `routine: false`, unticked in UI.
- FT-7 Not slow: every `not_slow` row has `in_stock_days_28 < 14`; none appears as a donor or pull-back.
- FT-8 New store: every move to BLR-05 carries `NEW_STORE`.
- FT-9 MZF-01: >= 1 move into MZF-01; MZF-01 end total <= 350.
- FT-10 Skip persistence: skip a move, export approvals.json to `state/`, rerun -> that `move_id` absent from `moves`, present in `blocked` as SKIPPED_BY_USER.
- FT-11 Diff: run `--date 2026-11-02` -> `diff.vs` = `moves-2026-10-31.json`, non-empty or explicitly empty.
- FT-12 Fallback: delete `out/`, open `index.html` -> renders `demo/moves.js`.
- FT-13 UI: 375 px width, no horizontal scroll; qty input cannot exceed proposed; reload keeps statuses.
- TC-I1 Independence: `grep -rE "engine|pandas|rules.json" validator/` returns nothing.

## Adversarial set (`validator/bad/`, each must exit 2 with the named rule)
| id | injected move(s) | expect |
|---|---|---|
| A1 | LKO-01 -> LKO-02, a KUR-02 size, qty 1 | R3 |
| A2 | two moves from one donor style, each within 30 d cover alone, together below | R5 (combination) |
| A3 | WH -> KNP-03 any sku qty 5 (store already 520/250) | R2 |
| A4 | WH -> a store/sku with in_transit > 0 already covering 30 d | R4 |
| A5 | donor qty that drops its category below min_display (e.g. MZF-01 Mojari) | R1 |
| A6 | qty x mrp = Rs 1,10,000 with `needs_approval:false` | R6 |
| A7 | WH -> BLR-01 with `lead_days: 3` | R7 |
| A8 | qty > donor on_hand | R8 |
| A9 | three WH moves of one sku summing > WH on_hand + inbound <= date | R8 |
| A10 | sku `PKG-BAG` | R8 |
| A11 | KNP-03 -> WH SHW-02-L qty 270 (quarantined) | R8 |
| A12 | same move split into two rows to dodge Rs 1 lakh (duplicate move_id) | R8 |
| A13 | from == to | R8 |
| A14 | qty 0, -3, 2.5 | R8 |
| A15 | to = "LKO-09" | R8 |
Live demo: `V --inject validator/bad/A1.json` -> red row "R3 flagship: LKO-01 KUR-02 protected".

## Reconciliation
- RC-1 Per move: units out of `from` == units into `to` (single qty field; validator asserts int > 0).
- RC-2 Network: sum(on_hand + in_transit) over all locations before == after applying all moves (moves only relocate).
- RC-3 Summary: `summary.units == sum(qty)`, `summary.value_mrp == sum(qty*mrp)`, `summary.moves == len(moves)`, `routine + exceptions == moves`.
- RC-4 Engine vs validator: engine's `evidence.from_cover_after` and validator's recomputed cover agree within 0.5 d for 10 random moves.

## Spot-check: 10 numbers (fill from engine `self_audit`, verify in Excel)
| # | Number | Formula | Engine | Excel | OK |
|---|---|---|---|---|---|
| 1 | Network units on hand | sum(stock_snapshot.on_hand, negatives -> 0), excl. packaging | | | |
| 2 | WH-KOL units | sum on_hand where location_id=WH-KOL (expect 15,407) | | | |
| 3 | KNP-03 fill % | (on_hand+in_transit)/250 (expect 208%; 88% excl. F1) | | | |
| 4 | MZF-01 fill % | same / 350 (expect 37%) | | | |
| 5 | Units in transit | sum in_transit (expect 55) | | | |
| 6 | Oct vs Sep units sold | sum qty by month, excl. packaging (expect 7,264 / 3,473) | | | |
| 7 | v for one move's SKU | sold_28 / max(in_stock_days_28, 7) | | | |
| 8 | cover for same | (on_hand+in_transit)/v | | | |
| 9 | Moves needing approval | count qty*mrp > 100000 | | | |
| 10 | Rs at MRP moved | sum(qty*mrp) | | | |

## Hand-verify 10 moves
Pick 4 WH_TO_STORE, 3 STORE_TO_STORE, 3 PULL_BACK (incl. one to BLR-05, one > Rs 1 lakh). For each fill: sold_28, in_stock_days_28, v, avail, cover before/after, lead, rule checks R1-R7 by hand, reason text matches numbers.
| move_id | sold_28 | days | v | avail | cover b/a | lead | rules ok | reason matches |
|---|---|---|---|---|---|---|---|---|

## Non-functional
### NFT-1 · run.py runtime — NFR-1
- Target: <= 60 s wall clock, demo laptop. Method: `time python engine/run.py --date 2026-10-31`, 3 runs, worst counts. Pass: all 3 <= 60 s.
### NFT-2 · page render — NFR-2
- Target: first render <= 2 s from `file://`. Method: DevTools Performance, real moves.js. Pass: <= 2 s.
### NFT-3 · 10-minute approval — NFR-3
- Method: teammate who did not build it, stopwatch, from page open to approved CSV export. Pass: <= 10 min. BLOCKED until T10.
### NFT-4 · validator independence — NFR-4
- Method: TC-I1 grep + A1-A15 all rejected. Pass: grep empty, 15/15 exit 2.
