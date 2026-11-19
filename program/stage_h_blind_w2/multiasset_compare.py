"""Field-by-field compare of the multi-asset blind lane (stage_h_blind/multiasset_blind) against the
48 golden cases of asset-conventions.md, auction.md, fx-rfq-venue.md, rates-futures-venue.md.

Mapping, fixed and committed BEFORE the first comparison (coordinator instruction 2026-11-18):
- Field names: the spec names of HR-100 are the blind lane's names; no rename is needed.
- Only the fields a golden states are compared. Extra blind fields are representation only and ignored:
  `tick` (eqc), `fraction` (rtc parse), `mid`/`time` (fxv stream), `buy_ticks`/`sell_ticks`/`gross`
  (fut 0004/0005), `entry_ticks`/`settle_ticks`/`pnl` (fut 0006), `label`, `fills`/`residual`/`cancelled`
  where the golden states only price, volume and imbalance, and `move_pips` where not stated.
- Decimal strings compare by value (Decimal), so "100.0000" == "100" and "15.625000" == "15.625" are
  REPRESENTATION-ONLY differences, not mismatches. Golden values printed to 9 dp compare at 5e-10 absolute.
- Integers compare exactly; dates and texts exactly; `null` only with `null`; errors by `error_code`.
- Lists compare in order, element by element (HR-100 fill order).
Classes: MATCH (identical text), REPRESENTATION-ONLY (equal by value, text differs), VALUE MISMATCH.

    python -I program/stage_h_blind_w2/multiasset_compare.py <blind_results.json>
Exit 1 if the frozen file's SHA-256 differs from the record or any case is a VALUE MISMATCH.
"""
import hashlib
import json
import sys
from decimal import Decimal

SHA = "b7fa4a939f2e4fc8b0b8b4247929c5fc41f8d01a3022fff9e230a8e23c2cfee5"
NINE_DP = {"rtc_h-0008", "rtc_h-0010"}
E = lambda c: {"status": "error", "error_code": c}  # noqa: E731

GOLD = {
    "eqc_h-0001": {"price": "10.00"}, "eqc_h-0002": {"price": "10.01"},
    "eqc_h-0003": {"price": "0.1234"}, "eqc_h-0004": {"price": "0.1235"},
    "eqc_h-0005": {"price": "1.0000"}, "eqc_h-0006": {"price": "25.00"},
    "eqc_h-0007": E("E_DOMAIN"), "eqc_h-0008": {"settle_date": "2026-11-23"},
    "fxc_h-0001": {"pip_value": "100", "currency": "USD"},
    "fxc_h-0002": {"pip_value": "10000", "currency": "JPY"},
    "fxc_h-0003": {"spot_date": "2026-11-18"}, "fxc_h-0004": {"spot_date": "2026-11-27"},
    "fxc_h-0005": {"spot_date": "2026-11-24"}, "fxc_h-0006": {"spot_date": "2026-11-23"},
    "fxc_h-0007": E("E_INPUT"),
    "rtc_h-0001": {"value": "99.5"}, "rtc_h-0002": {"value": "99.515625"},
    "rtc_h-0003": {"value": "99.5078125"}, "rtc_h-0004": {"value": "99.52734375"},
    "rtc_h-0005": {"text": "101-09+"}, "rtc_h-0006": E("E_DOMAIN"),
    "rtc_h-0007": {"tick_value": "15.625"}, "rtc_h-0008": {"price": "99.036287924"},
    "rtc_h-0009": {"price": "100"}, "rtc_h-0010": {"price": "98.736111111"},
    "auc_h-0001": {"price": "10.01", "volume": 300, "imbalance": -100},
    "auc_h-0002": {
        "fills": [{"id": "s1", "qty": 100}, {"id": "s2", "qty": 200}, {"id": "s4", "qty": 150}, {"id": "s5", "qty": 150}],
        "residual": [{"id": "s3", "qty": 300}, {"id": "s5", "qty": 100}, {"id": "s6", "qty": 100}]},
    "auc_h-0003": {"price": "10.01", "volume": 100, "imbalance": 0},
    "auc_h-0004": {"price": "10.02"}, "auc_h-0005": {"price": "10.01"},
    "auc_h-0006": {"price": "10.02", "volume": 150, "imbalance": 50},
    "auc_h-0007": {"price": None, "volume": 0}, "auc_h-0008": {"price": None, "volume": 0},
    "fxv_h-0001": {"quotes": [{"bid": "1.08502", "ask": "1.08522"}]},
    "fxv_h-0002": {"quotes": [{"bid": "1.08502", "ask": "1.08523"}]},
    "fxv_h-0003": {"outcome": "LL_PRICE"}, "fxv_h-0004": {"outcome": "FILL", "price": "1.0852"},
    "fxv_h-0005": {"outcome": "LL_RANDOM"}, "fxv_h-0006": {"outcome": "LL_PRICE"},
    "fxv_h-0007": {"outcome": "FILL", "price": "1.0852"}, "fxv_h-0008": {"outcome": "LL_PRICE"},
    "fxv_h-0009": {"outcome": "FILL", "price": "1.0852"},
    "fut_h-0001": {"ticks": 7073}, "fut_h-0002": {"text": "110-16+"}, "fut_h-0003": E("E_DOMAIN"),
    "fut_h-0004": {"pnl": "140.625"}, "fut_h-0005": {"pnl": "134.625"},
    "fut_h-0006": {"variation_margin": "-31.25"},
}
TEXT = {"currency", "settle_date", "spot_date", "text", "outcome", "id"}


def cmp(path, g, b, nine):
    """Return list of (path, class) for non-MATCH leaves."""
    if isinstance(g, dict):
        if not isinstance(b, dict):
            return [(path, "VALUE MISMATCH")]
        out = []
        for k, v in g.items():
            out += cmp(f"{path}/{k}", v, b.get(k, "<missing>"), nine) if k in b else [(f"{path}/{k}", "VALUE MISMATCH (missing)")]
        return out
    if isinstance(g, list):
        if not isinstance(b, list) or len(b) != len(g):
            return [(path, "VALUE MISMATCH (length)")]
        return [x for i, (gv, bv) in enumerate(zip(g, b)) for x in cmp(f"{path}[{i}]", gv, bv, nine)]
    if g is None or isinstance(g, int) or path.rsplit("/", 1)[-1] in TEXT:
        return [] if g == b else [(path, "VALUE MISMATCH")]
    if g == b:
        return []
    try:
        dg, db = Decimal(g), Decimal(b)
    except Exception:
        return [(path, "VALUE MISMATCH")]
    tol = Decimal("5e-10") if nine else Decimal(0)
    return [(path, "REPRESENTATION-ONLY")] if abs(dg - db) <= tol else [(path, f"VALUE MISMATCH {g} vs {b}")]


def main():
    raw = open(sys.argv[1], "rb").read()
    if hashlib.sha256(raw).hexdigest() != SHA:
        print("frozen blind file: SHA-256 differs from the record", file=sys.stderr)
        return 1
    blind = json.loads(raw)
    bad = 0
    for cid, g in GOLD.items():
        if cid not in blind:
            print(f"{cid}\tNOT COMPUTED")
            bad += 1
            continue
        b = blind[cid]
        if g.get("status") == "error":
            st = "MATCH" if b.get("error_code") == g["error_code"] else f"VALUE MISMATCH {b.get('error_code')}"
        else:
            d = cmp("", g, b, cid in NINE_DP)
            st = "MATCH" if not d else ("REPRESENTATION-ONLY" if all(c == "REPRESENTATION-ONLY" for _, c in d) else "VALUE MISMATCH")
            st += "" if not d else "\t" + "; ".join(f"{p}: {c}" for p, c in d)
        bad += st.startswith("VALUE") or st.startswith("NOT")
        print(f"{cid}\t{st}")
    print(f"golden cases {len(GOLD)}, blind cases {len(blind)}, not MATCH-or-REPR {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
