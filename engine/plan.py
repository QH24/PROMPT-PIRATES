"""Needs, ledger, candidate checks, moves, blocked. One check() for every move type."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd

from engine.load import WH, Inputs
from engine.metrics import lead_days

Move = dict
Blocked = dict
TIER_ORDER = {"S++": 0, "S+": 1, "A": 2, "B": 3}


def cl(x: float) -> int:
    return math.ceil(round(x, 9))


class Ledger:
    """The ONLY mutable stock state. on_hand is clamped at 0; in_transit counts as arriving."""

    def __init__(self, pos: pd.DataFrame, stores: pd.DataFrame, min_display: dict | None = None,
                 protected: set | None = None) -> None:
        self.min_display = min_display or {}
        self.protected = protected or set()
        self.stores_df = stores
        self.store = {r.store_id: r for r in stores.itertuples()}
        self.oh: dict = defaultdict(int)
        self.it: dict = defaultdict(int)
        self.style_oh: dict = defaultdict(int)
        self.cat_oh: dict = defaultdict(int)
        self.total: dict = defaultdict(int)
        self.attr: dict = {}          # static per (loc, sku): v, style, cat, mrp, thin, sold, quar
        self.v_style: dict = defaultdict(float)
        self.s2s_styles: set = set()   # (store, style) that gave a store->store move: R5 then judges ALL its outflow
        for r in pos.itertuples():
            k = (r.location_id, r.sku_id)
            oh = max(r.on_hand, 0)
            self.oh[k], self.it[k] = oh, r.in_transit
            if not r.quarantined:      # suspect units are not countable cover or display; they still fill capacity
                self.style_oh[(r.location_id, r.style_id)] += oh
                self.cat_oh[(r.location_id, r.category_md)] += oh
            self.total[r.location_id] += oh + r.in_transit
            self.v_style[(r.location_id, r.style_id)] += r.v
            self.attr[k] = (r.v, r.style_id, r.category_md, r.mrp, r.thin, r.sold_28, r.quarantined)

    def on_hand(self, loc: str, sku: str) -> int:
        return self.oh[(loc, sku)]

    def in_transit(self, loc: str, sku: str) -> int:
        return self.it[(loc, sku)]

    def style_on_hand(self, loc: str, style: str) -> int:
        return self.style_oh[(loc, style)]

    def cat_on_hand(self, loc: str, cat: str) -> int:
        return self.cat_oh[(loc, cat)]

    def store_total(self, loc: str) -> int:
        return self.total[loc]

    def apply(self, src: str, dst: str, sku: str, qty: int) -> None:
        _, style, cat, *_ = self.attr[(src, sku)]
        self.oh[(src, sku)] -= qty
        self.style_oh[(src, style)] -= qty
        self.cat_oh[(src, cat)] -= qty
        self.total[src] -= qty
        if dst == WH:
            self.oh[(dst, sku)] += qty
            self.style_oh[(dst, style)] += qty
            self.cat_oh[(dst, cat)] += qty
        else:
            self.it[(dst, sku)] += qty
            self.s2s_styles.add((src, style))
        self.total[dst] += qty


def check(ledger: Ledger, pos: pd.DataFrame, cfg: dict, src: str, dst: str, sku: str, qty: int) -> tuple[int, list[str]]:
    """Max allowed qty <= qty and the rule codes that cut it. Reads the Ledger only (pos kept for signature)."""
    a_src, a_dst = ledger.attr.get((src, sku)), ledger.attr.get((dst, sku))
    if a_src is None or a_dst is None:
        return 0, []
    if a_src[6] or a_dst[6]:
        return 0, ["DATA_SUSPECT"]
    have = ledger.on_hand(src, sku)
    if have <= 0:
        return 0, []
    q, codes = min(qty, have), []

    def cut(cap: int, code: str) -> None:
        nonlocal q
        if cap < q:
            q = max(cap, 0)
            codes.append(code)

    v, style, cat, _, thin, sold, _ = a_src
    s = ledger.store.get(src)
    if s is not None:
        if s.tier == "S++" and (src, style) in ledger.protected:
            cut(0, "FLAGSHIP")
        floor = ledger.min_display.get((s.tier, cat), 0)
        cut(ledger.cat_on_hand(src, cat) - floor, "MIN_DISPLAY")
        if dst == WH:        # pull-back: keep pullback_keep_days of sales
            cut(have - cl(v * cfg["pullback_keep_days"]), "DONOR_COVER")
            if (src, style) in ledger.s2s_styles:
                vs = ledger.v_style[(src, style)]
                cut(ledger.style_on_hand(src, style) - cl(vs * cfg["donor_rule_days"]), "DONOR_COVER")
        else:
            if thin and sold == 0:
                cut(0, "DONOR_COVER")
            avail = have + ledger.in_transit(src, sku)
            if v > 0 and avail / v < cfg["donor_min_cover_days"]:
                cut(0, "DONOR_COVER")
            cut(have - cl(v * cfg["donor_keep_days"]), "DONOR_COVER")
            vs = ledger.v_style[(src, style)]
            cut(ledger.style_on_hand(src, style) - cl(vs * cfg["donor_rule_days"]), "DONOR_COVER")
    d = ledger.store.get(dst)
    if d is not None:
        cut(d.stock_capacity_units - ledger.store_total(dst), "CAPACITY")
        vd = a_dst[0]
        av = ledger.on_hand(dst, sku) + ledger.in_transit(dst, sku)
        lead = lead_days(src, dst, ledger.stores_df)
        if vd > 0:
            if av >= cl(vd * cfg["target_cover_days"]):
                cut(0, "IN_TRANSIT")
            cut(cl(vd * (cfg["target_cover_days"] + lead)) - av, "IN_TRANSIT")
    return q, codes


def _events(cal: pd.DataFrame, run_date: date) -> dict:
    out = {}
    c = cal[cal.date >= run_date.isoformat()].sort_values(["date", "festival"], ascending=[True, False])
    for st, g in c.groupby("state"):
        for r in g.itertuples():
            if r.festival or r.is_wedding_date == 1:
                out[st] = (r.festival or "Wedding date", r.date)
                break
    return out


def plan(inp: Inputs, pos: pd.DataFrame, cfg: dict, skipped: set[str]) -> tuple[list[Move], list[Blocked]]:
    run, iso = inp.run_date, inp.run_date.isoformat()
    L = Ledger(pos, inp.stores, inp.min_display, inp.protected)
    st = L.store
    ev = _events(inp.calendar, run)
    ev_days = {s: (date.fromisoformat(d) - run).days for s, (_, d) in ev.items()}
    new_cut = run - timedelta(days=60)
    moves: list[Move] = []
    blocked: list[Blocked] = []
    seen_b: set = set()
    ids: set = set()
    info = {r.sku_id: r for r in inp.items.itertuples()}

    def block(src, dst, sku, qty, rule, detail):
        k = (src, dst, sku, rule)
        if k not in seen_b:
            seen_b.add(k)
            blocked.append({"from": src, "to": dst, "sku_id": sku, "qty_wanted": int(qty), "rule": rule, "detail": detail})

    # quarantine rows are always reported, never moved
    for r in inp.quarantine.itertuples():
        a = L.attr[(r.location_id, r.sku_id)]
        wc = "none" if pd.isna(r.weekly_close) else int(r.weekly_close)
        block(r.location_id, WH if r.location_id != WH else "", r.sku_id, max(r.on_hand, 0), "DATA_SUSPECT",
              f"{r.reason}: snapshot on_hand {r.on_hand} vs weekly close {wc}; hold for physical count")

    def evid(src, dst, sku, qty, kind, acc=0):
        v, style, cat, mrp, thin, sold, _ = L.attr[(dst if kind != "PULL_BACK" else src, sku)]
        a_s = L.attr[(src, sku)]
        row = pos_idx[(src, sku)]
        r0 = pos_idx[(dst, sku)]
        e = {"to_on_hand": L.on_hand(dst, sku) if kind == "PULL_BACK" else max(int(r0.on_hand), 0),
             "to_in_transit": L.in_transit(dst, sku) if kind == "PULL_BACK" else int(r0.in_transit),
             "to_v_week": None, "to_cover_before": None, "to_cover_after": None,
             "from_on_hand": L.on_hand(src, sku), "from_cover_before": None, "from_cover_after": None,
             "sold_28": int(sold), "in_stock_days_28": int(row.in_stock_days_28),
             "age_days": None if pd.isna(row.age_days) else int(row.age_days), "event": None}
        if kind != "PULL_BACK":
            av = e["to_on_hand"] + e["to_in_transit"]
            e["to_v_week"] = round(v * 7, 1)
            e["to_cover_before"] = round(av / v, 1)
            e["to_cover_after"] = round((av + acc + qty) / v, 1)
            e["sold_28"], e["in_stock_days_28"] = int(sold), int(pos_idx[(dst, sku)].in_stock_days_28)
        if kind == "STORE_TO_STORE":
            vs = L.v_style[(src, a_s[1])]
            so = L.style_on_hand(src, a_s[1])
            if vs > 0:
                e["from_cover_before"], e["from_cover_after"] = round(so / vs, 1), round((so - qty) / vs, 1)
        elif kind == "PULL_BACK":
            vv = a_s[0]
            if vv > 0:
                e["from_cover_before"] = round(L.on_hand(src, sku) / vv, 1)
                e["from_cover_after"] = round((L.on_hand(src, sku) - qty) / vv, 1)
        return e

    def emit(src, dst, sku, qty, kind, e):
        it = info[sku]
        lead = lead_days(src, dst, inp.stores)
        mrp = int(it.mrp)
        warns = []
        if kind == "PULL_BACK":
            if L.attr[(src, sku)][4]:
                warns.append("THIN_DATA")
        else:
            if L.attr[(dst, sku)][4] or (kind == "STORE_TO_STORE" and L.attr[(src, sku)][4]):
                warns.append("THIN_DATA")
        for loc in (src, dst):
            if loc in st and date.fromisoformat(st[loc].opened_on) > new_cut:
                warns.append("NEW_STORE")
                break
        if kind == "STORE_TO_STORE" and st[src].zone != st[dst].zone:
            warns.append("CROSS_ZONE")
        if kind != "PULL_BACK":
            floor = L.min_display.get((st[dst].tier, L.attr[(dst, sku)][2]), 0)
            if L.cat_on_hand(dst, L.attr[(dst, sku)][2]) < floor:
                warns.append("BELOW_MIN_DISPLAY_RECEIVER")
        appr = qty * mrp > cfg["approval_mrp_rs"]
        moves.append({
            "move_id": f"{src}>{dst}>{sku}", "type": kind, "from": src, "to": dst, "sku_id": sku,
            "style_id": it.style_id, "style_name": it.style_name, "category": it.category, "size": it.size,
            "qty": int(qty), "mrp": mrp, "value_mrp": int(qty * mrp), "lead_days": lead,
            "dispatch_on": iso, "arrives_on": (run + timedelta(days=lead)).isoformat(),
            "needs_approval": appr, "warnings": warns, "routine": (not appr) and not warns,
            "evidence": e, "finding_ids": [], "status": "Proposed"})
        ids.add(f"{src}>{dst}>{sku}")

    pos_idx = {(r.location_id, r.sku_id): r for r in pos.itertuples()}

    # 1. needs
    needs = []
    for r in pos.itertuples():
        if r.location_id == WH or r.quarantined or r.v <= 0:
            continue
        if r.cover_days >= cfg["under_cover_days"]:
            continue
        lead = lead_days(WH, r.location_id, inp.stores)
        n = cl(r.v * (cfg["target_cover_days"] + lead)) - r.avail
        if n <= 0:
            continue
        s = st[r.location_id]
        needs.append((r, n, (r.avail != 0, r.cover_days, ev_days.get(s.state, 10 ** 6),
                             TIER_ORDER[s.tier], r.location_id, r.sku_id)))
    needs.sort(key=lambda x: x[2])

    holders: dict = defaultdict(list)
    for (loc, sku), rr in pos_idx.items():
        if rr.on_hand > 0:
            holders[sku].append(loc)
    # avail==0 first: key (False < True) already sorts zero-avail ahead; keep that meaning

    # 2. fill each need
    for r, n, _ in needs:
        dst, sku = r.location_id, r.sku_id
        cands = []
        for src in holders[sku]:
            if src == dst:
                continue
            ex = L.on_hand(src, sku) if src == WH else L.on_hand(src, sku) - cl(L.attr[(src, sku)][0] * cfg["donor_keep_days"])
            cands.append((lead_days(src, dst, inp.stores), src != WH, -ex, src))
        cands.sort()
        rem = n
        for _, _, _, src in cands:
            if rem <= 0:
                break
            ok, codes = check(L, pos, cfg, src, dst, sku, rem)
            have = L.on_hand(src, sku)
            for c in codes:
                block(src, dst, sku, rem, c, f"{c} cut {min(rem, have)} to {ok} at {src} (on hand {have})")
            if ok <= 0:
                continue
            mid = f"{src}>{dst}>{sku}"
            if mid in skipped:
                block(src, dst, sku, ok, "SKIPPED_BY_USER", "skipped in approvals.json")
                continue
            if mid in ids:
                continue
            kind = "WH_TO_STORE" if src == WH else "STORE_TO_STORE"
            e = evid(src, dst, sku, ok, kind, n - rem)
            emit(src, dst, sku, ok, kind, e)
            moves[-1]["evidence"]["event"] = _event(ev.get(st[dst].state), run, cfg)
            L.apply(src, dst, sku, ok)
            rem -= ok
        if rem > 0:
            block("ANY", dst, sku, rem, "NO_SOURCE", f"WH and donors empty or cut; {rem} units still short")

    # 3. pull-backs (no store needs it after step 2)
    pb = []
    for r in pos.itertuples():
        if r.location_id == WH or r.quarantined or r.on_hand <= 0 or pd.isna(r.age_days):
            continue
        if r.age_days < cfg["pullback_age_days"]:
            continue
        slow = r.cover_days >= cfg["pullback_cover_days"] or (r.sold_28 == 0 and r.in_stock_days_28 >= 21)
        if slow:
            pb.append((-r.age_days, r.location_id, r.sku_id))
    for _, src, sku in sorted(pb):
        want = L.on_hand(src, sku) - cl(L.attr[(src, sku)][0] * cfg["pullback_keep_days"])
        if want <= 0:
            continue
        ok, codes = check(L, pos, cfg, src, WH, sku, want)
        for c in codes:
            block(src, WH, sku, want, c, f"{c} cut pull-back of {want} to {ok} at {src}")
        if ok <= 0:
            continue
        mid = f"{src}>{WH}>{sku}"
        if mid in skipped:
            block(src, WH, sku, ok, "SKIPPED_BY_USER", "skipped in approvals.json")
            continue
        e = evid(src, WH, sku, ok, "PULL_BACK")
        emit(src, WH, sku, ok, "PULL_BACK", e)
        L.apply(src, WH, sku, ok)
    return moves, blocked


def _event(e, run: date, cfg: dict):
    if not e:
        return None
    days = (date.fromisoformat(e[1]) - run).days
    return {"name": e[0], "date": e[1], "days_away": days} if days <= cfg["festival_lookahead_days"] else None


def _selfcheck() -> None:
    cfg = {"donor_keep_days": 45, "donor_min_cover_days": 60, "donor_rule_days": 30, "target_cover_days": 30,
           "pullback_keep_days": 60}
    stores = pd.DataFrame({"store_id": ["A", "B"], "city": ["X", "X"], "zone": ["North", "North"], "tier": ["S+", "A"],
                           "stock_capacity_units": [800, 800]})
    rows = [("A", 7, 0.1), ("B", 0, 1.0)]
    pos = pd.DataFrame([{"location_id": l, "sku_id": "K-M", "on_hand": o, "in_transit": 0, "avail": o, "sold_28": 0,
                         "in_stock_days_28": 28, "v": v, "cover_days": o / v, "age_days": 10.0, "thin": False,
                         "quarantined": False, "style_id": "K", "category_md": "Kurta Set", "mrp": 1000}
                        for l, o, v in rows])
    L = Ledger(pos, stores)
    # donor A: keep ceil(0.1*45)=5 of 7 -> give-room exactly 2
    assert check(L, pos, cfg, "A", "B", "K-M", 2) == (2, []), check(L, pos, cfg, "A", "B", "K-M", 2)
    L.apply("A", "B", "K-M", 2)
    q, codes = check(L, pos, cfg, "A", "B", "K-M", 2)
    assert q == 0 and "DONOR_COVER" in codes, (q, codes)
    assert L.on_hand("A", "K-M") == 5 and L.in_transit("B", "K-M") == 2 and L.store_total("B") == 2
    # quarantine blocks both directions
    pos.loc[1, "quarantined"] = True
    L2 = Ledger(pos, stores)
    assert check(L2, pos, cfg, "A", "B", "K-M", 1) == (0, ["DATA_SUSPECT"])
    print("plan.py self-check OK")


if __name__ == "__main__":
    _selfcheck()
