"""Per (location, sku) position frame: velocity, cover, age. Lead-time table."""
from __future__ import annotations

import math
from datetime import timedelta

import pandas as pd

from engine.load import WH, Inputs, md_category

_LEAD_WH = {"East": 3, "North": 4, "South": 6}
_geo_cache: dict = {}


def lead_days(src: str, dst: str, stores: pd.DataFrame) -> int:
    g = _geo_cache.get(id(stores))
    if g is None:
        g = _geo_cache[id(stores)] = {r.store_id: (r.city, r.zone) for r in stores.itertuples()}
    if WH in (src, dst):
        return _LEAD_WH[g[dst if src == WH else src][1]]   # A8: pull-back = outbound lead of that zone
    (c1, z1), (c2, z2) = g[src], g[dst]
    return 2 if c1 == c2 else 4 if z1 == z2 else 7


def build_position(inp: Inputs, cfg: dict, include_implied: bool = False) -> pd.DataFrame:
    """include_implied: add zero-stock rows for (store, sku) pairs that sold in the window but have no snapshot
    row (the snapshot omits some stock-outs). Default off = exactly the snapshot rows."""
    snap = inp.snap
    if include_implied:
        have = set(zip(snap.location_id, snap.sku_id))
        known = set(inp.items.sku_id)
        ex = inp.sales28[[(a, b) not in have and b in known for a, b in zip(inp.sales28.store_id, inp.sales28.sku_id)]]
        if len(ex):
            snap = pd.concat([snap, pd.DataFrame({
                "as_of_date": inp.as_of.isoformat(), "location_id": ex.store_id.values, "sku_id": ex.sku_id.values,
                "on_hand": 0, "in_transit": 0, "in_transit_arrives_on": "", "oldest_stock_received_on": "",
                "landed": 0, "inbound_in": 0})], ignore_index=True)
    s = snap.merge(inp.items[["sku_id", "style_id", "style_name", "category", "size", "mrp"]],
                       on="sku_id", how="inner")
    wk_start = (inp.as_of - timedelta(days=cfg["velocity_window_days"] - 7)).isoformat()
    w = inp.weekly[(inp.weekly.week_ending >= wk_start) & (inp.weekly.week_ending <= inp.as_of.isoformat())]
    isd = (w.groupby(["store_id", "sku_id"], as_index=False).days_in_stock.sum()
           .rename(columns={"store_id": "location_id", "days_in_stock": "in_stock_days_28"}))
    s = s.merge(isd, on=["location_id", "sku_id"], how="left")
    s = s.merge(inp.sales28.rename(columns={"store_id": "location_id"}), on=["location_id", "sku_id"], how="left")
    s[["in_stock_days_28", "sold_28"]] = s[["in_stock_days_28", "sold_28"]].fillna(0).astype(int)
    s["on_hand"] = s.on_hand.astype(int)
    s["in_transit"] = s.in_transit.astype(int)
    s["avail"] = s.on_hand.clip(lower=0) + s.in_transit
    s["v"] = s.sold_28 / s.in_stock_days_28.clip(lower=7)          # D7
    s["cover_days"] = (s.avail / s.v).where(s.v > 0, math.inf)
    oldest = pd.to_datetime(s.oldest_stock_received_on.where(s.oldest_stock_received_on != ""))
    s["age_days"] = (pd.Timestamp(inp.run_date) - oldest).dt.days
    iswh = s.location_id == WH
    s["thin"] = (s.in_stock_days_28 < cfg["thin_data_days"]) & ~iswh
    q = set(zip(inp.quarantine.location_id, inp.quarantine.sku_id))
    s["quarantined"] = [k in q for k in zip(s.location_id, s.sku_id)]
    s["category_md"] = s.category.map(md_category)
    cols = ["location_id", "sku_id", "on_hand", "in_transit", "avail", "sold_28", "in_stock_days_28", "v",
            "cover_days", "age_days", "thin", "quarantined", "style_id", "category_md", "mrp",
            "style_name", "category", "size"]
    return s[cols].sort_values(["location_id", "sku_id"]).reset_index(drop=True)
