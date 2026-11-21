"""Read data/*.csv (all as text), roll forward to run_date, quarantine bad rows."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

import pandas as pd

WH = "WH-KOL"
ACC = "Accessories (Safa/Mala/Stole)"
SCHEMA = {
    "stores": "store_id,city,state,zone,tier,stock_capacity_units,opened_on",
    "items": "sku_id,style_id,style_name,category,size,mrp,is_packaging",
    "stock_snapshot": "as_of_date,location_id,sku_id,on_hand,in_transit,in_transit_arrives_on,oldest_stock_received_on",
    "stock_weekly": "week_ending,store_id,sku_id,closing_on_hand,days_in_stock",
    "bills": "bill_id,bill_date,store_id",
    "bill_lines": "bill_id,sku_id,qty",
    "warehouse_inbound": "expected_date,sku_id,qty",
    "calendar": "date,state,festival,is_wedding_date",
    "min_display": "tier,category,min_display_units",
    "flagship_protected": "store_id,rank,style_id",
}


class Inputs(NamedTuple):
    stores: pd.DataFrame
    items: pd.DataFrame
    snap: pd.DataFrame        # rolled forward; extra cols: landed (transit->on_hand), inbound_in (WH)
    weekly: pd.DataFrame
    sales28: pd.DataFrame
    inbound: pd.DataFrame
    calendar: pd.DataFrame
    min_display: dict
    protected: set
    quarantine: pd.DataFrame
    as_of: date
    run_date: date
    monthly: dict             # {"2026-09": units, "2026-10": units}, packaging excluded
    row_counts: dict


def md_category(cat: str) -> str:
    return ACC if cat in ("Safa", "Mala", "Stole") else cat


def _read(data_dir: Path, name: str) -> pd.DataFrame:
    p = data_dir / f"{name}.csv"
    if not p.exists():
        raise SystemExit(f"input error: {p} missing")
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    for col in SCHEMA[name].split(","):
        if col not in df.columns:
            raise SystemExit(f"input error: {name}.csv:{col} missing")
    return df


def load_all(data_dir: Path, run_date: date) -> Inputs:
    data_dir = Path(data_dir)
    d = {n: _read(data_dir, n) for n in SCHEMA}
    stores, items = d["stores"], d["items"]
    stores["stock_capacity_units"] = stores["stock_capacity_units"].astype(int)
    items["mrp"] = items["mrp"].astype(int)
    pkg = set(items.loc[items.is_packaging == "1", "sku_id"])
    items = items[items.is_packaging != "1"].reset_index(drop=True)

    snap = d["stock_snapshot"]
    as_of = date.fromisoformat(snap["as_of_date"].iloc[0])
    snap = snap[~snap.sku_id.isin(pkg)].copy()
    for c in ("on_hand", "in_transit"):
        snap[c] = snap[c].astype(int)
    iso = run_date.isoformat()
    # A1: in-transit that has arrived by run_date becomes on_hand
    land = (snap.in_transit > 0) & (snap.in_transit_arrives_on != "") & (snap.in_transit_arrives_on <= iso)
    snap["landed"] = snap.in_transit.where(land, 0)
    snap["on_hand"] = snap.on_hand + snap.landed
    snap["in_transit"] = snap.in_transit - snap.landed
    # A1: warehouse inbound due by run_date joins WH on_hand
    ib = d["warehouse_inbound"]
    ib = ib[~ib.sku_id.isin(pkg)].copy()
    ib["qty"] = ib["qty"].astype(int)
    due = ib[ib.expected_date <= iso].groupby("sku_id").qty.sum()
    snap["inbound_in"] = 0
    wh = snap.location_id == WH
    snap.loc[wh, "inbound_in"] = snap.loc[wh, "sku_id"].map(due).fillna(0).astype(int)
    snap["on_hand"] = snap.on_hand + snap.inbound_in
    missing = sorted(set(due.index) - set(snap.loc[wh, "sku_id"]))
    if missing:
        extra = pd.DataFrame({"as_of_date": snap.as_of_date.iloc[0], "location_id": WH, "sku_id": missing,
                              "on_hand": [int(due[s]) for s in missing], "in_transit": 0,
                              "in_transit_arrives_on": "", "oldest_stock_received_on": "",
                              "landed": 0, "inbound_in": [int(due[s]) for s in missing]})
        snap = pd.concat([snap, extra], ignore_index=True)
    snap = snap.reset_index(drop=True)

    weekly = d["stock_weekly"]
    weekly = weekly[~weekly.sku_id.isin(pkg)].copy()
    weekly["closing_on_hand"] = weekly.closing_on_hand.astype(int)
    weekly["days_in_stock"] = weekly.days_in_stock.astype(int)

    # D6 quarantine: negative snapshot on_hand, or snapshot != weekly close for week_ending == as_of
    wk = weekly[weekly.week_ending == as_of.isoformat()][["store_id", "sku_id", "closing_on_hand"]]
    wk = wk.rename(columns={"store_id": "location_id", "closing_on_hand": "weekly_close"})
    q = snap[["location_id", "sku_id", "on_hand"]].merge(wk, on=["location_id", "sku_id"], how="left")
    neg = q.on_hand < 0
    mis = q.weekly_close.notna() & (q.on_hand != q.weekly_close) & (snap.landed.values == 0) & ~neg
    # (rows that changed through roll-forward are compared on the as_of snapshot only)
    q["reason"] = ""
    q.loc[neg, "reason"] = "NEGATIVE_ON_HAND"
    q.loc[mis, "reason"] = "SNAPSHOT_WEEKLY_MISMATCH"
    quarantine = q[q.reason != ""][["location_id", "sku_id", "reason", "on_hand", "weekly_close"]].reset_index(drop=True)

    # sold_28 = bill qty over as_of-27 .. as_of
    lo = (as_of - timedelta(days=27)).isoformat()
    bills = d["bills"]
    b = bills[(bills.bill_date >= lo) & (bills.bill_date <= as_of.isoformat())][["bill_id", "store_id"]]
    bl = d["bill_lines"][["bill_id", "sku_id", "qty"]]
    bl = bl[~bl.sku_id.isin(pkg)].copy()
    bl["qty"] = bl.qty.astype(int)
    sales28 = (bl.merge(b, on="bill_id").groupby(["store_id", "sku_id"], as_index=False).qty.sum()
               .rename(columns={"qty": "sold_28"}))
    mb = bills[["bill_id", "bill_date"]].assign(m=bills.bill_date.str[:7])
    mm = bl.merge(mb[mb.m.isin(["2026-09", "2026-10"])], on="bill_id").groupby("m").qty.sum()
    monthly = {k: int(v) for k, v in mm.items()}

    md = {(r.tier, r.category): int(r.min_display_units) for r in d["min_display"].itertuples()}
    protected = {(r.store_id, r.style_id) for r in d["flagship_protected"].itertuples()}
    cal = d["calendar"].copy()
    cal["is_wedding_date"] = cal.is_wedding_date.astype(int)
    counts = {f"{n}.csv": len(df) for n, df in d.items()}
    return Inputs(stores, items, snap, weekly, sales28, ib, cal, md, protected, quarantine,
                  as_of, run_date, monthly, counts)
