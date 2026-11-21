"""Reason templates, findings, not_slow, self-audit, diff, atomic writers."""
from __future__ import annotations

import json
import math
import os
from datetime import date
from pathlib import Path

import pandas as pd

from engine.load import WH, Inputs
from engine.plan import Move

CSV_COLUMNS = "move_id,from,to,sku_id,style_name,size,qty,value_mrp,dispatch_on,arrives_on,reason".split(",")
ASSUMPTIONS = [
    "A1: Today = --date; stock = 31 Oct snapshot rolled forward (arrived in-transit and due WH inbound added); sales after 31 Oct unknown.",
    "A2: Rs 1,00,000 approval threshold is per move line (qty x MRP), not per batch.",
    "A3: No seasonal multiplier; the 28-day window already holds the October festive rate. Festivals/weddings only raise priority.",
    "A4: New store BLR-05 and any SKU with < 14 in-stock days: velocity flagged THIN_DATA; moves to it are exceptions.",
    "A5: Donor-cover rule applied at style level (rule text: 'for that style'); engine also checks SKU level.",
    "A6: Min display is a donor-side rule at category level; Safa+Mala+Stole summed.",
    "A7: Capacity counts on_hand + in_transit, negatives clamped to 0, quarantined units included as reported.",
    "A8: Pull-back lead time = WH->store lead for that store's zone.",
    "A9: Packaging SKUs (PKG-BAG, PKG-COVER, PKG-BOX) excluded everywhere.",
    "A10: Cross-zone store->store moves (7 days) are allowed but always an exception.",
]


def _days(x) -> str:
    return f"about {round(x)} days" if x is not None and round(x) != 1 else "about 1 day"


def _nice(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')}"


def _rate(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".") if v >= 0.1 else "under 0.1"


def reason(m: Move) -> str:
    """Plain English, one or two short sentences. Every number comes from m['evidence']."""
    e = m["evidence"]
    if m["type"] == "WH_TO_STORE":
        have = "has none left" if not e["to_on_hand"] else f"has {e['to_on_hand']} left"
        if e["to_in_transit"]:
            have += f" (+{e['to_in_transit']} on the way)"
        out = (f"{m['to']} {have} and sells about {_rate(e['to_v_week'])} a week. "
               f"Sending {m['qty']} from the warehouse")
        if e["to_cover_after"] is not None:
            out += f" covers it for {_days(e['to_cover_after'])}"
        out += f"; arrives {_nice(m['arrives_on'])}"
        if e["event"]:
            out += f", {e['event']['name']} in {e['event']['days_away']} days"
        return out + "."
    if m["type"] == "STORE_TO_STORE":
        have = "has none left" if not e["to_cover_before"] else f"has {_days(e['to_cover_before'])} of stock"
        keep = (f"{m['from']} still keeps {_days(e['from_cover_after'])} of stock"
                if e["from_cover_after"] is not None else f"{m['from']} has not sold this in 4 weeks")
        return (f"Move {m['qty']} from {m['from']} to {m['to']}. {m['to']} {have} and sells about "
                f"{_rate(e['to_v_week'])} a week; {keep}. Arrives {_nice(m['arrives_on'])}.")
    cover = f" ({_days(e['from_cover_before'])} of stock)" if e["from_cover_before"] is not None else ""
    return (f"Bring {m['qty']} back to the warehouse from {m['from']}: it has sat {e['age_days']} days and "
            f"sold {e['sold_28']} in the last 4 weeks{cover}. No store needs it.")


def _ids(moves, pred) -> list:
    return [m["move_id"] for m in moves if pred(m)]


def not_slow(pos: pd.DataFrame) -> list[dict]:
    p = pos[(pos.location_id != WH) & ~pos.quarantined & (pos.on_hand > 0) & (pos.sold_28 == 0)
            & (pos.in_stock_days_28 < 14)]
    return [{"store_id": r.location_id, "sku_id": r.sku_id, "on_hand": int(r.on_hand),
             "in_stock_days_28": int(r.in_stock_days_28),
             "note": f"zero sales but only {int(r.in_stock_days_28)} in-stock days in 28: unavailable, not slow"}
            for r in p.itertuples()]


def findings(inp: Inputs, pos: pd.DataFrame, moves: list[Move], blocked: list[dict]) -> list[dict]:
    st = inp.stores.set_index("store_id")
    stores = pos[pos.location_id != WH]
    mrp = {(r.location_id, r.sku_id): r.mrp for r in pos.itertuples()}
    cap = st.stock_capacity_units
    tot = stores.assign(a=stores.on_hand.clip(lower=0) + stores.in_transit).groupby("location_id").a.sum()
    out: list[dict] = []

    def add(fid, title, kind, evidence, value, ids, action):
        for m in moves:
            if m["move_id"] in ids:
                m["finding_ids"].append(fid)
        out.append({"id": fid, "title": title, "kind": kind, "evidence": evidence, "value_rs": int(value),
                    "move_ids": ids, "action": action})

    q = inp.quarantine
    for fid, reason_code, title in (("F1", "SNAPSHOT_WEEKLY_MISMATCH", "Snapshot disagrees with weekly close"),
                                    ("F2", "NEGATIVE_ON_HAND", "Negative on-hand in snapshot")):
        rows = q[q.reason == reason_code]
        ev = [{"location_id": r.location_id, "sku_id": r.sku_id, "snapshot_on_hand": int(r.on_hand),
               "weekly_close": None if pd.isna(r.weekly_close) else int(r.weekly_close)} for r in rows.itertuples()]
        val = sum(max(r.on_hand, 0) * mrp[(r.location_id, r.sku_id)] for r in rows.itertuples())
        if fid == "F1" and ev:
            r0 = rows.iloc[0]
            c = int(cap[r0.location_id])
            ev[0].update(capacity=c, fill_pct_reported=round(100 * tot[r0.location_id] / c),
                         fill_pct_without=round(100 * (tot[r0.location_id] - r0.on_hand) / c))
        add(fid, title, "DATA_ERROR", ev, val, [],
            "Not moved (blocked DATA_SUSPECT); hold for physical count" if fid == "F1"
            else "Not moved (blocked DATA_SUSPECT); fix the snapshot row")

    mz = stores[stores.location_id == "MZF-01"]
    moj = mz[mz.category_md == "Mojari"].on_hand.clip(lower=0).sum()
    floor = inp.min_display.get((st.tier["MZF-01"], "Mojari"), 0)
    ids = _ids(moves, lambda m: m["to"] == "MZF-01")
    add("F3", "MZF-01 is under-stocked", "REAL_PROBLEM",
        {"store_id": "MZF-01", "units": int(tot["MZF-01"]), "capacity": int(cap["MZF-01"]),
         "fill_pct": round(100 * tot["MZF-01"] / cap["MZF-01"]), "mojari_on_hand": int(moj), "mojari_min": floor},
        0, ids, "Replenish from WH" if ids else "No move: no source stock passes the rules")

    nos = stores[(stores.v > 0) & (stores.avail == 0) & ~stores.quarantined]
    lost = (nos.v * 7 * nos.mrp).sum()
    ids = _ids(moves, lambda m: m["type"] != "PULL_BACK" and m["evidence"]["to_on_hand"] + m["evidence"]["to_in_transit"] == 0)
    add("F4", "Selling SKUs with no stock", "REAL_PROBLEM",
        {"pairs": len(nos), "lost_rs_per_week": int(lost)}, lost, ids,
        "Fill from WH / donors" if ids else "No move: no source stock passes the rules")

    old = stores[(stores.age_days >= 120) & (stores.on_hand > 0)]
    ids = _ids(moves, lambda m: m["type"] != "WH_TO_STORE" and (m["evidence"]["age_days"] or 0) >= 120)
    add("F5", "Stock ageing over 120 days", "REAL_PROBLEM",
        {"rows": len(old), "units": int(old.on_hand.sum())}, (old.on_hand * old.mrp).sum(), ids,
        "Pull back or redistribute" if ids else "No move: ageing stock is protected or below keep levels")

    ns = not_slow(pos)
    add("F6", "Zero sales is not always slow", "CONTEXT",
        {"rows": len(ns), "units": sum(r["on_hand"] for r in ns)}, 0, [],
        "Would have been flagged slow, correctly not touched (no move by design)")

    b5 = stores[(stores.location_id == "BLR-05") & (stores.category == "Sherwani")]
    add("F7", "BLR-05 is a new store", "CONTEXT",
        {"store_id": "BLR-05", "opened_on": str(st.opened_on["BLR-05"]), "sherwani_on_hand": int(b5.on_hand.clip(lower=0).sum()),
         "sherwani_min": inp.min_display.get((st.tier["BLR-05"], "Sherwani"), 0)},
        0, _ids(moves, lambda m: "NEW_STORE" in m["warnings"]), "Moves involving it are exceptions (thin history)")

    cal = inp.calendar[(inp.calendar.date >= inp.run_date.isoformat()) & ((inp.calendar.festival != "") | (inp.calendar.is_wedding_date == 1))]
    wed = sorted(cal[cal.is_wedding_date == 1].date.unique())
    fest = {r.festival + " " + r.date for r in cal[cal.festival != ""].itertuples()}
    add("F8", "Festive season ahead", "CONTEXT",
        {"oct_units": inp.monthly.get("2026-10", 0), "sep_units": inp.monthly.get("2026-09", 0),
         "festivals": sorted(fest)[:6], "wedding_first": wed[0] if wed else None, "wedding_last": wed[-1] if wed else None},
        0, _ids(moves, lambda m: m["evidence"]["event"] is not None), "Priority and reason text only; no forecast multiplier")

    it = pos[(pos.in_transit > 0)]
    landed = int(inp.snap.landed.sum())
    intr = {(r.location_id, r.sku_id) for r in it.itertuples()}
    resent = _ids(moves, lambda m: (m["to"], m["sku_id"]) in intr)
    add("F9", "Stock already in transit is counted", "CONTEXT",
        {"in_transit_units": int(it.in_transit.sum()) + landed, "rows": len(it) + int((inp.snap.landed > 0).sum()),
         "moves_to_in_transit_pairs": len(resent)}, 0, resent,
        "Counted as arriving; only topped up if cover is still < 14d")
    return out


def self_audit(inp: Inputs, pos: pd.DataFrame, moves: list[Move]) -> list[dict]:
    stores = pos[pos.location_id != WH]
    st = inp.stores.set_index("store_id")
    tot = stores.assign(a=stores.on_hand.clip(lower=0) + stores.in_transit).groupby("location_id").a.sum()
    k = inp.quarantine[inp.quarantine.location_id == "KNP-03"]
    kn = int(tot["KNP-03"])
    a = [
        ("Network units on hand", int(pos.on_hand.clip(lower=0).sum()), "sum(stock_snapshot.on_hand, negatives -> 0), excl. packaging, after roll-forward"),
        ("WH-KOL units", int(pos[pos.location_id == WH].on_hand.sum()), "sum on_hand where location_id=WH-KOL"),
        ("KNP-03 fill %", round(100 * kn / st.stock_capacity_units["KNP-03"]),
         f"(on_hand+in_transit)/{st.stock_capacity_units['KNP-03']}; {round(100 * (kn - int(k.on_hand.sum())) / st.stock_capacity_units['KNP-03'])}% excl. F1"),
        ("MZF-01 fill %", round(100 * tot["MZF-01"] / st.stock_capacity_units["MZF-01"]),
         f"(on_hand+in_transit)/{st.stock_capacity_units['MZF-01']}"),
        ("Units in transit", int(pos.in_transit.sum() + inp.snap.landed.sum()), "sum in_transit in snapshot (incl. already landed by --date)"),
        ("Oct vs Sep units sold", f"{inp.monthly.get('2026-10', 0)} / {inp.monthly.get('2026-09', 0)}", "sum bill_lines.qty by bill month, excl. packaging"),
    ]
    m0 = next((m for m in moves if m["type"] != "PULL_BACK"), None)
    if m0:
        r = pos[(pos.location_id == m0["to"]) & (pos.sku_id == m0["sku_id"])].iloc[0]
        cov = (r.on_hand + r.in_transit) / r.v if r.v else None
        a.append((f"v for {m0['to']} {m0['sku_id']}", round(float(r.v), 4), f"sold_28 {r.sold_28} / max(in_stock_days_28 {r.in_stock_days_28}, 7)"))
        a.append(("cover for same (days, before moves)", None if cov is None else round(float(cov), 1), "(on_hand+in_transit)/v"))
    a.append(("Moves needing approval", sum(m["needs_approval"] for m in moves), "count qty*mrp > 100000"))
    a.append(("Rs at MRP moved", sum(m["value_mrp"] for m in moves), "sum(qty*mrp)"))
    return [{"label": l, "value": v, "formula": f} for l, v, f in a]


def diff(prev_path: Path | None, moves: list[Move]) -> dict:
    d = {"vs": None, "added": [], "removed": [], "qty_changed": []}
    if prev_path is None:
        return d
    prev = {m["move_id"]: m["qty"] for m in json.loads(Path(prev_path).read_text())["moves"]}
    now = {m["move_id"]: m["qty"] for m in moves}
    d["vs"] = Path(prev_path).name
    d["added"] = sorted(set(now) - set(prev))
    d["removed"] = sorted(set(prev) - set(now))
    d["qty_changed"] = [{"move_id": k, "was": prev[k], "now": now[k]} for k in sorted(set(now) & set(prev)) if prev[k] != now[k]]
    return d


def _clean(o):
    if isinstance(o, float) and (math.isinf(o) or math.isnan(o)):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if hasattr(o, "item"):   # numpy scalar
        return _clean(o.item())
    return o


def dumps(payload: dict) -> str:
    return json.dumps(_clean(payload), indent=1, allow_nan=False)


def write_all(out_dir: Path, run_date: date, payload: dict) -> None:
    """moves-<date>.json, moves.json, moves.js, CSV header files; each temp-written then os.replace()d."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    js = dumps(payload)
    head = ",".join(CSV_COLUMNS) + "\n"
    files = {f"moves-{run_date.isoformat()}.json": js, "moves.json": js,
             "moves.js": f"window.MOVES = {js};\n", "approved.csv": head, "pick-list.csv": head}
    tmp = {}
    try:
        for name, text in files.items():
            t = out_dir / (name + ".tmp")
            t.write_text(text)
            tmp[name] = t
    except Exception:
        for t in tmp.values():
            t.unlink(missing_ok=True)
        raise
    for name, t in tmp.items():
        os.replace(t, out_dir / name)
