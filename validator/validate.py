#!/usr/bin/env python3
"""Independent rule checker for a moves.json file.

Written from data/rules.csv, data/min_display.csv, data/lead_times.csv and the
moves.json contract only. Recomputes every number from data/*.csv; ignores any
`evidence` block in the moves. Judges the whole list at once (end-state
aggregation), never move by move.

Usage: validate.py --moves PATH --data DIR [--inject PATH] [--out PATH]
Exit:  0 clean, 2 violations, 1 input error.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from fractions import Fraction
from math import ceil
from pathlib import Path

# Own constants, typed from data/rules.csv and data/lead_times.csv.
WH = "WH-KOL"
APPROVAL_RS = 100000          # "worth more than Rs 1,00,000 at MRP"
DONOR_COVER_DAYS = 30         # "below 30 days of cover for that style"
IN_TRANSIT_COVER_DAYS = 30    # R4: already covered for 30 d -> do not send
IN_TRANSIT_MAX_DAYS = 37      # R4: 30 d cover + longest route (7 d)
WH_LEAD = {"East": 3, "North": 4, "South": 6}
S2S_SAME_CITY, S2S_SAME_ZONE, S2S_OTHER_ZONE = 2, 4, 7
ACCESSORIES = "Accessories (Safa/Mala/Stole)"
ACCESSORY_CATS = {"Safa", "Mala", "Stole"}
WINDOW_DAYS = 28
TYPES = {"WH_TO_STORE", "STORE_TO_STORE", "PULL_BACK"}
RULES = {"R1": "min display", "R2": "capacity", "R3": "flagship", "R4": "in-transit",
         "R5": "donor cover", "R6": "approval", "R7": "lead time", "R8": "conservation"}


class InputError(Exception):
    pass


def read_csv(data_dir, name, cols):
    path = data_dir / name
    if not path.exists():
        raise InputError(f"{name}: file missing")
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    missing = [c for c in cols if rows and c not in rows[0]]
    if not rows or missing:
        raise InputError(f"{name}:{','.join(missing) or 'no rows'} missing")
    return rows


def d(s):
    return date.fromisoformat(s)


def load(data_dir, run_date):
    stores = {r["store_id"]: r for r in read_csv(data_dir, "stores.csv",
              ["store_id", "city", "zone", "tier", "stock_capacity_units"])}
    items = {r["sku_id"]: r for r in read_csv(data_dir, "items.csv",
             ["sku_id", "style_id", "category", "mrp", "is_packaging"])}
    min_display = {(r["tier"], r["category"]): int(r["min_display_units"])
                   for r in read_csv(data_dir, "min_display.csv", ["tier", "category", "min_display_units"])}
    protected = {(r["store_id"], r["style_id"])
                 for r in read_csv(data_dir, "flagship_protected.csv", ["store_id", "style_id"])}
    snap = read_csv(data_dir, "stock_snapshot.csv",
                    ["as_of_date", "location_id", "sku_id", "on_hand", "in_transit", "in_transit_arrives_on"])
    as_of = d(snap[0]["as_of_date"])
    run_date = run_date or as_of
    if run_date < as_of:
        raise InputError(f"run date {run_date} is before snapshot {as_of}")

    weekly_close, in_stock_days = {}, defaultdict(int)
    first_week = as_of - timedelta(days=WINDOW_DAYS - 7)
    for r in read_csv(data_dir, "stock_weekly.csv",
                      ["week_ending", "store_id", "sku_id", "closing_on_hand", "days_in_stock"]):
        key, wk = (r["store_id"], r["sku_id"]), d(r["week_ending"])
        if wk == as_of:
            weekly_close[key] = int(r["closing_on_hand"])
        if first_week <= wk <= as_of:
            in_stock_days[key] += int(r["days_in_stock"])

    start = as_of - timedelta(days=WINDOW_DAYS - 1)
    bill_store = {r["bill_id"]: r["store_id"]
                  for r in read_csv(data_dir, "bills.csv", ["bill_id", "bill_date", "store_id"])
                  if start <= d(r["bill_date"]) <= as_of}
    sold = defaultdict(int)
    for r in read_csv(data_dir, "bill_lines.csv", ["bill_id", "sku_id", "qty"]):
        s = bill_store.get(r["bill_id"])
        if s:
            sold[(s, r["sku_id"])] += int(r["qty"])

    raw, on_hand, avail, quarantine = {}, defaultdict(int), defaultdict(int), set()
    for r in snap:
        key = (r["location_id"], r["sku_id"])
        oh, it = int(r["on_hand"]), int(r["in_transit"] or 0)
        raw[key] = oh
        arrived = it if it and r["in_transit_arrives_on"] and d(r["in_transit_arrives_on"]) <= run_date else 0
        on_hand[key] += max(oh, 0) + arrived       # rolled forward to run date
        avail[key] += max(oh, 0) + it              # date-invariant for stores
        if oh < 0 or (key in weekly_close and weekly_close[key] != oh):
            quarantine.add(key)
    for r in read_csv(data_dir, "warehouse_inbound.csv", ["expected_date", "sku_id", "qty"]):
        if d(r["expected_date"]) <= run_date:
            on_hand[(WH, r["sku_id"])] += int(r["qty"])
            avail[(WH, r["sku_id"])] += int(r["qty"])

    def v(loc, sku):
        return Fraction(sold[(loc, sku)], max(in_stock_days[(loc, sku)], 7))

    return dict(stores=stores, items=items, min_display=min_display, protected=protected,
                on_hand=on_hand, avail=avail, raw=raw, quarantine=quarantine, v=v,
                as_of=as_of, run_date=run_date)


def md_cat(category):
    return ACCESSORIES if category in ACCESSORY_CATS else category


def route_days(src, dst, stores):
    if src == WH:
        return WH_LEAD[stores[dst]["zone"]]
    if dst == WH:                                   # pull-back: same as WH->store for that zone
        return WH_LEAD[stores[src]["zone"]]
    a, b = stores[src], stores[dst]
    if a["city"] == b["city"]:
        return S2S_SAME_CITY
    return S2S_SAME_ZONE if a["zone"] == b["zone"] else S2S_OTHER_ZONE


def validate(moves, D):
    stores, items = D["stores"], D["items"]
    per_rule = {r: {"checks": 0, "violations": 0} for r in RULES}
    details = []

    def chk(rule, ok, move_ids, detail):
        per_rule[rule]["checks"] += 1
        if not ok:
            per_rule[rule]["violations"] += 1
            for mid in move_ids:
                details.append({"move_id": mid, "rule": rule, "detail": f"{rule} {RULES[rule]}: {detail}"})
        return ok

    # --- R8 per-move shape; only well-formed moves go on to aggregation ---
    good, seen_id, seen_key = [], defaultdict(int), defaultdict(int)
    for i, m in enumerate(moves):
        mid = str(m.get("move_id") or f"#{i}")
        seen_id[mid] += 1
        seen_key[(m.get("from"), m.get("to"), m.get("sku_id"))] += 1
    for i, m in enumerate(moves):
        mid = str(m.get("move_id") or f"#{i}")
        src, dst, sku, q = m.get("from"), m.get("to"), m.get("sku_id"), m.get("qty")
        locs_ok = src in stores or src == WH, dst in stores or dst == WH
        ok = all([
            chk("R8", type(q) is int and q > 0, [mid], f"qty {q!r} must be an int > 0"),
            chk("R8", src != dst, [mid], f"from == to ({src})"),
            chk("R8", locs_ok[0], [mid], f"unknown from location {src!r}"),
            chk("R8", locs_ok[1], [mid], f"unknown to location {dst!r}"),
            chk("R8", sku in items, [mid], f"unknown sku {sku!r}"),
            chk("R8", seen_id[mid] == 1, [mid], f"duplicate move_id {mid}"),
            chk("R8", seen_key[(src, dst, sku)] == 1, [mid], f"({src},{dst},{sku}) split over several rows"),
        ])
        if sku in items:
            ok &= chk("R8", items[sku]["is_packaging"] != "1", [mid], f"packaging sku {sku}")
        for loc in (src, dst):
            ok &= chk("R8", (loc, sku) not in D["quarantine"], [mid],
                      f"({loc},{sku}) quarantined: snapshot {D['raw'].get((loc, sku))} disagrees with weekly close")
        if all(locs_ok) and src != dst:
            want = ("WH_TO_STORE" if src == WH else "PULL_BACK" if dst == WH else "STORE_TO_STORE")
            ok &= chk("R8", m.get("type") == want, [mid], f"type {m.get('type')!r} but {src}->{dst} is {want}")
        if ok:
            good.append((mid, m))

    out_sku, in_sku = defaultdict(list), defaultdict(list)
    for mid, m in good:
        out_sku[(m["from"], m["sku_id"])].append((mid, m))
        in_sku[(m["to"], m["sku_id"])].append((mid, m))

    def qsum(lst):
        return sum(m["qty"] for _, m in lst)

    def ids(lst):
        return [mid for mid, _ in lst]

    # R8: combined outflow per (loc, sku) within stock at run date (WH incl. inbound <= date)
    for (loc, sku), lst in out_sku.items():
        chk("R8", qsum(lst) <= D["on_hand"][(loc, sku)], ids(lst),
            f"{loc} {sku} sends {qsum(lst)} but holds {D['on_hand'][(loc, sku)]}")
    before = sum(D["avail"].values())
    after = defaultdict(int, D["avail"])
    for mid, m in good:
        after[(m["from"], m["sku_id"])] -= m["qty"]
        after[(m["to"], m["sku_id"])] += m["qty"]
    chk("R8", sum(after.values()) == before, ids(good), f"network units {before} -> {sum(after.values())}")

    # Per-move rules: R3, R6, R7
    for mid, m in good:
        src, dst, sku = m["from"], m["to"], m["sku_id"]
        it = items[sku]
        if src in stores:
            chk("R3", not (stores[src]["tier"] == "S++" and (src, it["style_id"]) in D["protected"]), [mid],
                f"{src} {it['style_id']} protected")
        value = m["qty"] * int(it["mrp"])
        chk("R6", value <= APPROVAL_RS or m.get("needs_approval") is True, [mid],
            f"{m['qty']} x Rs {it['mrp']} = Rs {value} > {APPROVAL_RS} without needs_approval")
        lead = route_days(src, dst, stores)
        chk("R7", m.get("lead_days") == lead, [mid], f"lead_days {m.get('lead_days')!r}, route {src}->{dst} is {lead}")
        try:
            gap = (d(m["arrives_on"]) - d(m["dispatch_on"])).days
        except (KeyError, TypeError, ValueError):
            gap = None
        chk("R7", gap == m.get("lead_days"), [mid],
            f"arrives_on {m.get('arrives_on')} - dispatch_on {m.get('dispatch_on')} != lead_days {m.get('lead_days')}")

    # Donor-side stock excludes quarantined units (conservative: a suspect count cannot make room).
    def donor_on_hand(loc, sku):
        return 0 if (loc, sku) in D["quarantine"] else D["on_hand"][(loc, sku)]

    by_loc_cat, by_loc_style = defaultdict(int), defaultdict(int)
    for (loc, sku) in list(D["on_hand"]):
        if loc in stores and sku in items and items[sku]["is_packaging"] != "1":
            by_loc_cat[(loc, md_cat(items[sku]["category"]))] += donor_on_hand(loc, sku)
            by_loc_style[(loc, items[sku]["style_id"])] += donor_on_hand(loc, sku)

    out_cat, out_style, s2s_styles = defaultdict(list), defaultdict(list), set()
    for mid, m in good:
        if m["from"] in stores:
            it = items[m["sku_id"]]
            out_cat[(m["from"], md_cat(it["category"]))].append((mid, m))
            out_style[(m["from"], it["style_id"])].append((mid, m))
            if m["to"] in stores:
                s2s_styles.add((m["from"], it["style_id"]))

    # R1: every giving store, every category it gives from, end on_hand >= min display
    for (loc, cat), lst in out_cat.items():
        floor = D["min_display"].get((stores[loc]["tier"], cat))
        end = by_loc_cat[(loc, cat)] - qsum(lst)
        chk("R1", floor is None or end >= floor, ids(lst),
            f"{loc} {cat} ends at {end} < min {floor} ({stores[loc]['tier']})")

    # R5: store->store donor style end on_hand / v_style >= 30 (all outflow of that style counted)
    style_skus = defaultdict(list)
    for sku, it in items.items():
        style_skus[it["style_id"]].append(sku)
    for (loc, style) in s2s_styles:
        lst = out_style[(loc, style)]
        vs = sum(D["v"](loc, s) for s in style_skus[style])
        end = by_loc_style[(loc, style)] - qsum(lst)
        cover = "inf" if vs == 0 else f"{float(end / vs):.1f}"
        chk("R5", vs == 0 or end >= DONOR_COVER_DAYS * vs, ids(lst),
            f"{loc} {style} ends at {end} units = {cover} d cover < {DONOR_COVER_DAYS} d")

    # R2: every receiving store, end total (on_hand + in_transit) + in - out <= capacity
    totals = defaultdict(int)
    for (loc, _), n in D["avail"].items():
        totals[loc] += n
    in_store, out_store = defaultdict(list), defaultdict(int)
    for mid, m in good:
        out_store[m["from"]] += m["qty"]
        if m["to"] in stores:
            in_store[m["to"]].append((mid, m))
    for loc, lst in in_store.items():
        cap = int(stores[loc]["stock_capacity_units"])
        end = totals[loc] + qsum(lst) - out_store[loc]
        chk("R2", end <= cap, ids(lst), f"{loc} ends at {end} > capacity {cap}")

    # R4: per receiving (store, sku), all inflow combined, against stock already on hand + in transit
    for (loc, sku), lst in in_sku.items():
        if loc not in stores:
            continue
        v, have, q = D["v"](loc, sku), D["avail"][(loc, sku)], qsum(lst)
        chk("R4", have < ceil(v * IN_TRANSIT_COVER_DAYS), ids(lst),
            f"{loc} {sku} already has {have} (on hand + in transit) >= {IN_TRANSIT_COVER_DAYS} d at v={float(v):.3f}/d")
        room = ceil(v * IN_TRANSIT_MAX_DAYS) - have
        chk("R4", q <= room, ids(lst), f"{loc} {sku} receives {q} > room {room} (v={float(v):.3f}/d)")

    viol = sum(r["violations"] for r in per_rule.values())
    return {"checked": len(moves), "checks": sum(r["checks"] for r in per_rule.values()),
            "violations": viol, "rules": list(RULES), "per_rule": per_rule,
            "offending_move_ids": sorted({x["move_id"] for x in details}), "details": details,
            "run_date": D["run_date"].isoformat(), "as_of": D["as_of"].isoformat()}


def read_moves(path):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InputError(f"{path}: {e}")
    if isinstance(doc, list):
        return {}, doc
    if not isinstance(doc, dict) or not isinstance(doc.get("moves"), list):
        raise InputError(f"{path}: no moves[] list")
    if not all(isinstance(m, dict) for m in doc["moves"]):
        raise InputError(f"{path}: every move must be an object")
    return doc, doc["moves"]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--moves", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--inject")
    p.add_argument("--out")
    a = p.parse_args(argv)
    try:
        doc, moves = read_moves(a.moves)
        if a.inject:
            moves = moves + read_moves(a.inject)[1]
        run = doc.get("run") or {}
        run_date = d(run["date"]) if run.get("date") else None
        res = validate(moves, load(Path(a.data), run_date))
    except (InputError, ValueError, KeyError) as e:
        print(f"input error: {e}", file=sys.stderr)
        return 1
    print(f"{'rule':<18}{'checks':>8}{'violations':>12}")
    for r, name in RULES.items():
        pr = res["per_rule"][r]
        print(f"{r + ' ' + name:<18}{pr['checks']:>8}{pr['violations']:>12}")
    print(f"{res['violations']} violations in {res['checks']} checks over {res['checked']} moves")
    for x in res["details"]:
        print(f"  {x['move_id']}: {x['detail']}")
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    return 2 if res["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
