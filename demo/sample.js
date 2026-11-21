// Hand-written fixture for UI development (contract: docs/plan/lld.md)
window.MOVES = {
 "schema": 1,
 "run": {
  "date": "2026-10-31",
  "as_of": "2026-10-31",
  "generated_at": "2026-11-21T09:00:00",
  "git_sha": "sample",
  "inputs": {
   "stock_snapshot.csv": 2400,
   "bills.csv": 52000
  }
 },
 "summary": {
  "moves": 6,
  "units": 47,
  "value_mrp": 582800,
  "routine": 4,
  "exceptions": 2,
  "blocked": 2,
  "by_type": {
   "WH_TO_STORE": 4,
   "STORE_TO_STORE": 1,
   "PULL_BACK": 1
  }
 },
 "validator": {
  "checked": 6,
  "violations": 0,
  "rules": [
   "R1",
   "R2",
   "R3",
   "R4",
   "R5",
   "R6",
   "R7",
   "R8"
  ],
  "details": []
 },
 "moves": [
  {
   "move_id": "WH-KOL>MZF-01>KUR-02-M",
   "type": "WH_TO_STORE",
   "from": "WH-KOL",
   "to": "MZF-01",
   "sku_id": "KUR-02-M",
   "style_id": "KUR-02",
   "style_name": "Silk Kurta Ivory",
   "category": "Kurta",
   "size": "M",
   "qty": 12,
   "mrp": 6500,
   "value_mrp": 78000,
   "lead_days": 3,
   "dispatch_on": "2026-10-31",
   "arrives_on": "2026-11-03",
   "needs_approval": false,
   "warnings": [],
   "routine": true,
   "reason": "Send 12 from WH: 2 on hand, sells 5.5/wk, cover 3d -> 18d, arrives 2026-11-03, Diwali in 8 days",
   "evidence": {
    "to_on_hand": 2,
    "to_in_transit": 0,
    "to_v_week": 5.5,
    "to_cover_before": 3,
    "to_cover_after": 18,
    "from_on_hand": 140,
    "from_cover_before": null,
    "from_cover_after": null,
    "sold_28": 22,
    "in_stock_days_28": 28,
    "age_days": null,
    "event": {
     "name": "Diwali",
     "date": "2026-11-08",
     "days_away": 8
    }
   },
   "finding_ids": [
    "F3",
    "F4"
   ],
   "status": "Proposed"
  },
  {
   "move_id": "WH-KOL>MZF-01>MOJ-01-9",
   "type": "WH_TO_STORE",
   "from": "WH-KOL",
   "to": "MZF-01",
   "sku_id": "MOJ-01-9",
   "style_id": "MOJ-01",
   "style_name": "Embroidered Mojari",
   "category": "Mojari",
   "size": "9",
   "qty": 8,
   "mrp": 3200,
   "value_mrp": 25600,
   "lead_days": 3,
   "dispatch_on": "2026-10-31",
   "arrives_on": "2026-11-03",
   "needs_approval": false,
   "warnings": [],
   "routine": true,
   "reason": "Send 8 from WH: 0 on hand, sells 2.1/wk, cover 0d -> 27d, arrives 2026-11-03, Diwali in 8 days",
   "evidence": {
    "to_on_hand": 0,
    "to_in_transit": 0,
    "to_v_week": 2.1,
    "to_cover_before": 0,
    "to_cover_after": 27,
    "from_on_hand": 60,
    "from_cover_before": null,
    "from_cover_after": null,
    "sold_28": 8,
    "in_stock_days_28": 28,
    "age_days": null,
    "event": {
     "name": "Diwali",
     "date": "2026-11-08",
     "days_away": 8
    }
   },
   "finding_ids": [
    "F3"
   ],
   "status": "Proposed"
  },
  {
   "move_id": "WH-KOL>BLR-05>SHW-01-40",
   "type": "WH_TO_STORE",
   "from": "WH-KOL",
   "to": "BLR-05",
   "sku_id": "SHW-01-40",
   "style_id": "SHW-01",
   "style_name": "Wedding Sherwani Gold",
   "category": "Sherwani",
   "size": "40",
   "qty": 3,
   "mrp": 48000,
   "value_mrp": 144000,
   "lead_days": 6,
   "dispatch_on": "2026-10-31",
   "arrives_on": "2026-11-06",
   "needs_approval": false,
   "warnings": [
    "NEW_STORE",
    "THIN_DATA"
   ],
   "routine": false,
   "reason": "Send 3 from WH: 2 on hand, sells 1.4/wk, cover 10d -> 40d, arrives 2026-11-06, Diwali in 8 days",
   "evidence": {
    "to_on_hand": 2,
    "to_in_transit": 0,
    "to_v_week": 1.4,
    "to_cover_before": 10,
    "to_cover_after": 40,
    "from_on_hand": 20,
    "from_cover_before": null,
    "from_cover_after": null,
    "sold_28": 2,
    "in_stock_days_28": 12,
    "age_days": null,
    "event": {
     "name": "Diwali",
     "date": "2026-11-08",
     "days_away": 8
    }
   },
   "finding_ids": [
    "F7"
   ],
   "status": "Proposed"
  },
  {
   "move_id": "WH-KOL>PAT-01>SHW-03-42",
   "type": "WH_TO_STORE",
   "from": "WH-KOL",
   "to": "PAT-01",
   "sku_id": "SHW-03-42",
   "style_id": "SHW-03",
   "style_name": "Royal Sherwani Maroon",
   "category": "Sherwani",
   "size": "42",
   "qty": 4,
   "mrp": 62000,
   "value_mrp": 248000,
   "lead_days": 4,
   "dispatch_on": "2026-10-31",
   "arrives_on": "2026-11-04",
   "needs_approval": true,
   "warnings": [],
   "routine": false,
   "reason": "Send 4 from WH: 1 on hand, sells 2.8/wk, cover 3d -> 31d, arrives 2026-11-04, Diwali in 8 days",
   "evidence": {
    "to_on_hand": 1,
    "to_in_transit": 0,
    "to_v_week": 2.8,
    "to_cover_before": 3,
    "to_cover_after": 31,
    "from_on_hand": 30,
    "from_cover_before": null,
    "from_cover_after": null,
    "sold_28": 11,
    "in_stock_days_28": 28,
    "age_days": null,
    "event": {
     "name": "Diwali",
     "date": "2026-11-08",
     "days_away": 8
    }
   },
   "finding_ids": [
    "F4"
   ],
   "status": "Proposed"
  },
  {
   "move_id": "LKO-02>LKO-01>KUR-05-L",
   "type": "STORE_TO_STORE",
   "from": "LKO-02",
   "to": "LKO-01",
   "sku_id": "KUR-05-L",
   "style_id": "KUR-05",
   "style_name": "Cotton Kurta Sky",
   "category": "Kurta",
   "size": "L",
   "qty": 6,
   "mrp": 2400,
   "value_mrp": 14400,
   "lead_days": 2,
   "dispatch_on": "2026-10-31",
   "arrives_on": "2026-11-02",
   "needs_approval": false,
   "warnings": [],
   "routine": true,
   "reason": "Move 6 LKO-02->LKO-01: LKO-02 keeps 74d cover, LKO-01 has 4d and sells 4.2/wk, 2d",
   "evidence": {
    "to_on_hand": 2,
    "to_in_transit": 0,
    "to_v_week": 4.2,
    "to_cover_before": 4,
    "to_cover_after": 21,
    "from_on_hand": 40,
    "from_cover_before": 110,
    "from_cover_after": 74,
    "sold_28": 17,
    "in_stock_days_28": 28,
    "age_days": null,
    "event": null
   },
   "finding_ids": [
    "F4"
   ],
   "status": "Proposed"
  },
  {
   "move_id": "DEL-03>WH-KOL>JKT-04-M",
   "type": "PULL_BACK",
   "from": "DEL-03",
   "to": "WH-KOL",
   "sku_id": "JKT-04-M",
   "style_id": "JKT-04",
   "style_name": "Nehru Jacket Wool",
   "category": "Jacket",
   "size": "M",
   "qty": 14,
   "mrp": 5200,
   "value_mrp": 72800,
   "lead_days": 4,
   "dispatch_on": "2026-10-31",
   "arrives_on": "2026-11-04",
   "needs_approval": false,
   "warnings": [],
   "routine": true,
   "reason": "Pull back 14 to WH: 143d old, sold 0 in 28d, cover 190d, no store needs it",
   "evidence": {
    "to_on_hand": 0,
    "to_in_transit": 0,
    "to_v_week": 0,
    "to_cover_before": 0,
    "to_cover_after": 0,
    "from_on_hand": 20,
    "from_cover_before": 190,
    "from_cover_after": 60,
    "sold_28": 0,
    "in_stock_days_28": 28,
    "age_days": 143,
    "event": null
   },
   "finding_ids": [
    "F5"
   ],
   "status": "Proposed"
  }
 ],
 "blocked": [
  {
   "from": "KNP-03",
   "to": "WH-KOL",
   "sku_id": "SHW-02-L",
   "qty_wanted": 270,
   "rule": "DATA_SUSPECT",
   "detail": "Snapshot says 300 but weekly close is 0; hold for physical count"
  },
  {
   "from": "BLR-01",
   "to": "MZF-01",
   "sku_id": "KUR-02-M",
   "qty_wanted": 10,
   "rule": "FLAGSHIP",
   "detail": "KUR-02 is flagship-protected at BLR-01"
  }
 ],
 "findings": [
  {
   "id": "F1",
   "title": "KNP-03 holds 300 units that were never counted",
   "kind": "DATA_ERROR",
   "evidence": "Snapshot SHW-02-L on hand 300 vs weekly close 0. This one row is Rs 83,09,700 and causes the 208% capacity reading.",
   "value_rs": 8309700,
   "move_ids": [],
   "action": "Count the shelf before anyone moves it"
  },
  {
   "id": "F3",
   "title": "MZF-01 is under-stocked going into Diwali",
   "kind": "REAL_PROBLEM",
   "evidence": "128 of 350 units; Mojari 5 is below the minimum of 8.",
   "value_rs": 76000,
   "move_ids": [
    "WH-KOL>MZF-01>KUR-02-M",
    "WH-KOL>MZF-01>MOJ-01-9"
   ],
   "action": "Send from WH-KOL"
  }
 ],
 "not_slow": [
  {
   "store_id": "BLR-05",
   "sku_id": "KUR-09-S",
   "on_hand": 0,
   "in_stock_days_28": 3,
   "note": "Zero sales but only 3 days in stock: unavailable, not slow"
  }
 ],
 "self_audit": [
  {
   "label": "Network units before",
   "value": 1240,
   "formula": "sum on_hand + in_transit"
  },
  {
   "label": "Network units after",
   "value": 1240,
   "formula": "before, moves conserve units"
  },
  {
   "label": "Moves above Rs 1,00,000",
   "value": 0,
   "formula": "count qty*mrp > 100000"
  },
  {
   "label": "Moves needing approval",
   "value": 1,
   "formula": "needs_approval true"
  }
 ],
 "assumptions": [
  "A1: Today is --date; in-transit arriving by then counts as on hand.",
  "A2: The Rs 1,00,000 approval threshold is per move line.",
  "A4: New store BLR-05 and SKUs with under 14 in-stock days are THIN_DATA; moves to them are exceptions."
 ],
 "diff": {
  "vs": null,
  "added": [],
  "removed": [],
  "qty_changed": []
 }
};
