# Validator notes: how the rule text was read

Written from `data/rules.csv`, `min_display.csv`, `lead_times.csv` and the lld moves.json contract.

1. **R1/R5 donor stock excludes quarantined units.** A suspect count (KNP-03 SHW-02-L 300) can't make room for a donor. For R2 capacity, quarantined units count as reported (A7), so the rule is strict on both sides.
2. **R1 applies only to categories a store actually gives from**, pull-backs included ("a store giving stock away must not drop below it"). A store already below min that gives nothing in that category is not a violation. Donor end stock = on_hand rolled forward to `run.date` minus every outflow. Incoming moves are not counted, because they are still in transit when the donor dispatches.
3. **R5 counts all outflow of the style** (store-to-store and pull-back) and is checked for every style with at least one store-to-store outflow. Cover = on_hand / v_style, following the lld's "style end on_hand". The rule text only says "days of cover", which could also mean on_hand + in_transit. The on_hand reading is stricter.
4. **R4 is the lld formula, not the literal rule text.** The text says "in transit counts as arriving, do not send it again". The lld turns that into: avail >= ceil(v*30) means don't send, and qty <= ceil(v*37) - avail. Two consequences:
   - With v = 0, any send is a violation.
   - 37 = 30 d + the longest route (7 d). Neither number appears in rules.csv.
   Inflow from all moves into one (store, sku) is summed.
5. **R8 adds checks the lld table doesn't list:**
   - one row per (from, to, sku), because D8 says splitting is forbidden even under different move_ids
   - `type` must match from/to (WH_TO_STORE / STORE_TO_STORE / PULL_BACK)
6. **A6:** no MRP in items.csv divides Rs 1,10,000 exactly, so the file uses 15 x 7199 = Rs 1,07,985.
7. **A1 also trips R5, and this is correct.** LKO-01 KUR-02 is already at about 27 d style cover (65 units, v_style 2.40/d), so any donation of it breaks R5 as well as R3.
8. **Velocity window** is anchored at the snapshot `as_of_date` (2026-10-31), not at `run.date`, because sales after the snapshot are unknown (A1). Stock is rolled forward to `run.date`: in-transit that has arrived counts as on_hand, and WH inbound with expected_date <= date is added.
