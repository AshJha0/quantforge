"""Stage K wave 2 lane A goldens: FRTB DRC and RRAO (K-8a, suite drc_k) and FRTB IMA (K-8f, suite ima_k).

Specs: specifications/06-risk/frtb-drc-rrao.md and specifications/06-risk/frtb-ima.md; rulings
specifications/stage-k-rulings-w2.md (KR-50 to KR-69, and KR-300 to KR-309 of the lane A section).
This oracle is written from the specs, in exact rational arithmetic (fractions) where the rules are
rational and in mpmath at 50 digits where they are not; it does not import quantforge_core. Parameters
are read from specifications/tables/stage_k/*.json (KR-50), never retyped.

Every value case is asserted before anything is written:
- the 31 hand cases that the DR-H2 blind lane re-derived (program/STAGE_K_BLIND_W2.md) against the
  hidden expected file program/stage_h_blind_w2/k2_expected.json, field by field, at the KR-67
  compare tolerance max(1e-12 |e|, 1e-15);
- the other 20 value cases against the numbers printed in the spec tables (at the printed digits);
- the printed Basel figures (MAR22.16 FAQ, MAR22.45, MAR32.42 p-values, MAR33.12 FAQ4 and FAQ5);
- SciPy (independent library, reported, not counted: D6 precedent) on every PLA statistic and on the
  two normal-ES cases.
The generator stops at the first failure.

    cd oracle/python && uv run python -W ignore gen_stage_k_w2a.py
"""
import json
import math
from collections import Counter
import re
from datetime import date, timedelta
from fractions import Fraction as Fr
from pathlib import Path

import mpmath as mp
from scipy import integrate, stats

from qf_oracle import common
from qf_oracle.common import Suite, f

mp.mp.dps = 50
G = "oracle/python/gen_stage_k_w2a.py"
SPEC_A = "specifications/06-risk/frtb-drc-rrao.md"
SPEC_F = "specifications/06-risk/frtb-ima.md"
ROOT = Path(__file__).resolve().parents[2]
TABLES = {k: json.loads((ROOT / f"specifications/tables/stage_k/{k}.json").read_text("utf-8"))
          for k in ("mar22_drc", "mar23_rrao", "mar31_rfet", "mar32_pla", "mar33_ima")}
EXPECTED = json.loads((ROOT / "program/stage_h_blind_w2/k2_expected.json").read_text("utf-8"))["cases"]
LABEL = "regulatory formula on caller inputs; not a regulatory return"
RW_SOURCE = "securitisation risk weights supplied by the caller (CRE40-CRE44 not implemented)"
ORACLE = "fractions and mpmath 50 digits (independent oracle, gen_stage_k_w2a.py)"
BLIND = "blind re-derivation DR-H2 2026-11-19 (program/STAGE_K_BLIND_W2.md): MATCH"
# K-8f second blind lane (8 of 8 MATCH; first recorded by hand in a01f4a81, now owned here).
BLIND_IMA2 = "blind re-derivation DR-H2 2026-11-19 (second lane, stage_k_blind/ima2/compare_output.txt, program/STAGE_K_BLIND_W2.md): MATCH"
NOT_COUNTED_SCIPY = "not counted: D6 precedent (a library primitive computing the same quantity, as btk_k SciPy binom)"
LIMIT = {"absolute": 1e-15, "relative": 1e-12}  # KR-67 and A1 of both specs
TAGS_A = ["stage_k", "frtb_drc"]
TAGS_F = ["stage_k", "frtb_ima"]


def entry(table, key):
    return next(e["value"] for e in TABLES[table]["entries"] if e["key"] == key)


def check(ok, what):
    if not ok:
        raise SystemExit(f"FAILED: {what}")
    common.note(f"check MATCH: {what}")


def close(v, e):
    if isinstance(e, (bool, str)) or e is None:
        return v == e and type(v) is type(e)
    return not isinstance(v, bool) and abs(v - e) <= max(1e-12 * abs(e), 1e-15)


def get(o, path):
    for part in re.findall(r"[^.\[\]]+|\[[^\]]+\]", path):
        if part.startswith("["):
            key = part[1:-1]
            if isinstance(o, list):
                o = o[int(key)] if key.isdigit() else next(x for x in o if key in (x.get("id"), x.get("bucket"), x.get("obligor")))
            else:
                o = o[key]
        else:
            o = o[part]
    return o


def against_blind(cid, out):
    for fld in EXPECTED[cid]["fields"]:
        v = get(out, fld["path"])
        check(close(v, fld["value"]), f"{cid} {fld['path']} = {v!r} against k2_expected {fld['value']!r}")


def printed(v, text):
    """Within half a unit of the last printed digit (or 1e-12 relative, whichever is larger)."""
    e = float(text)
    dec = len(text.split(".")[1]) if "." in text else 0
    return abs(v - e) <= max(0.5 * 10.0 ** -dec, 1e-12 * abs(e))


class Named(Suite):
    """A suite whose case ids are the spec's (drc_k-0001, ctp_k-0002, drc_ke-0003, ...)."""

    def add_as(self, cid, *a, **k):
        self.add(*a, **k)
        self.cases[-1]["case_id"] = cid
        return self.cases[-1]


# ---- K-8a oracle (MAR22, MAR23) ---------------------------------------------------------------------------
LGD = {"COVERED": Fr(entry("mar22_drc", "lgd.covered_bond")), "SENIOR": Fr(entry("mar22_drc", "lgd.senior_debt")),
       "NON_SENIOR": Fr(entry("mar22_drc", "lgd.non_senior_debt")), "EQUITY": Fr(entry("mar22_drc", "lgd.equity"))}
RANK = {"COVERED": 4, "SENIOR": 3, "NON_SENIOR": 2, "EQUITY": 1}
RW = {r: Fr(entry("mar22_drc", "rw." + {"UNRATED": "Unrated", "DEFAULTED": "Defaulted"}.get(r, r)))
      for r in ("AAA", "AA", "A", "BBB", "BB", "B", "CCC", "UNRATED", "DEFAULTED")}
FLOOR = Fr(entry("mar22_drc", "maturity_weight_floor"))
HORIZON = Fr(entry("mar22_drc", "capital_horizon_years"))
CTP_HALF = Fr(entry("mar22_drc", "ctp_cross_index_factor"))
RRAO_W = {"EXOTIC": Fr(entry("mar23_rrao", "rw.exotic_underlying")), "OTHER": Fr(entry("mar23_rrao", "rw.other_residual_risk"))}


def Q(x):
    return Fr(x) if not isinstance(x, float) else Fr(x)  # binary64 inputs are exact rationals


def weight(m):
    m = Q(m)
    return Fr(1) if m >= HORIZON else max(m, FLOOR)


def jtd(p):
    lgd = LGD[p["seniority"]] if p.get("lgd_applies", True) else Fr(1)
    n, mv = Q(p["notional"]), Q(p["market_value"])
    raw = lgd * n + (mv - n)
    return max(raw, Fr(0)) if n > 0 else min(raw, Fr(0)) if n < 0 else Fr(0)


def net_obligor(items):
    """KR-53: shorts by descending rank (ties: input order), each against eligible longs by ascending rank."""
    longs = [[r, v] for r, v in items if v > 0]
    shorts = [(r, -v) for r, v in items if v < 0]
    order = sorted(range(len(longs)), key=lambda k: (longs[k][0], k))
    rest = Fr(0)
    for k in sorted(range(len(shorts)), key=lambda k: (-shorts[k][0], k)):
        rank, need = shorts[k]
        for j in order:
            if longs[j][0] >= rank and need > 0:
                use = min(need, longs[j][1])
                longs[j][1] -= use
                need -= use
        rest -= need
    return sum((v for _, v in longs), Fr(0)), rest


def bucket(pairs):
    lo, sh = sum((l for _, l, _ in pairs), Fr(0)), sum((-s for _, _, s in pairs), Fr(0))
    wl, ws = sum((rw * l for rw, l, _ in pairs), Fr(0)), sum((rw * -s for rw, _, s in pairs), Fr(0))
    hbr = lo / (lo + sh) if lo + sh > 0 else None
    drc = max(wl - hbr * ws, Fr(0)) if hbr is not None else Fr(0)
    return {"hbr": None if hbr is None else f(hbr), "wtd_long": f(wl), "wtd_short": f(ws), "drc": f(drc)}, drc


def o_nonsec(inp):
    pos, ratings = inp["positions"], inp["ratings"]
    rows, per = [], {}
    bucket_of = {}
    for p in pos:
        j, w = jtd(p), weight(p["maturity_years"])
        rows.append({"id": p["id"], "gross_jtd": f(j), "weight": f(w), "scaled_jtd": f(w * j)})
        per.setdefault(p["obligor"], []).append((RANK[p["seniority"]], w * j))
        bucket_of[p["obligor"]] = p["bucket"]
    obligors, by_bucket = [], {}
    for name in sorted(per):
        nl, ns = net_obligor(per[name])
        rw = RW[ratings[name]]
        obligors.append({"obligor": name, "net_long": f(nl), "net_short": f(ns), "rw": f(rw)})
        by_bucket.setdefault(bucket_of[name], []).append((rw, nl, ns))
    buckets, total = [], Fr(0)
    for b in ("CORPORATE", "SOVEREIGN", "LOCAL_GOV"):
        if b in by_bucket:
            out, d = bucket(by_bucket[b])
            buckets.append({"bucket": b, **out})
            total += d
    return {"positions": sorted(rows, key=lambda r: r["id"]), "obligors": obligors, "buckets": buckets,
            "drc": f(total), "label": LABEL}


def netted(pos, key):
    nets, rws = {}, {}
    for p in pos:
        k = tuple(p[x] for x in key)
        nets[k] = nets.get(k, Fr(0)) + weight(p["maturity_years"]) * Q(p["market_value"])
        rws[k] = Q(p["rw"])
    return nets, rws


def scaled_rows(pos):
    return sorted(({"id": p["id"], "weight": f(weight(p["maturity_years"])),
                    "scaled_jtd": f(weight(p["maturity_years"]) * Q(p["market_value"]))} for p in pos), key=lambda r: r["id"])


def o_sec(inp):
    nets, rws = netted(inp["positions"], ("bucket", "pool", "tranche"))
    by = {}
    for k, n in nets.items():
        by.setdefault(k[0], []).append((rws[k], max(n, Fr(0)), min(n, Fr(0))))
    buckets, total = [], Fr(0)
    for b in sorted(by):
        out, d = bucket(by[b])
        buckets.append({"bucket": b, **out})
        total += d
    return {"positions": scaled_rows(inp["positions"]), "buckets": buckets, "drc": f(total), "label": LABEL, "rw_source": RW_SOURCE}


def ctp_agg(ds):
    return max(sum((max(d, Fr(0)) + CTP_HALF * min(d, Fr(0)) for d in ds), Fr(0)), Fr(0))


def o_ctp(inp):
    if "bucket_drc" in inp:
        return {"drc": f(ctp_agg([Q(x) for x in inp["bucket_drc"]])), "label": LABEL, "rw_source": RW_SOURCE}
    nets, rws = netted(inp["positions"], ("index", "series", "tranche"))
    lo = sum((n for n in nets.values() if n > 0), Fr(0))
    sh = sum((-n for n in nets.values() if n < 0), Fr(0))
    hbr = lo / (lo + sh) if lo + sh > 0 else None
    by = {}
    for k, n in nets.items():
        by.setdefault(k[0], []).append((rws[k], n))
    buckets, ds = [], []
    for b in sorted(by):
        wl = sum((rw * n for rw, n in by[b] if n > 0), Fr(0))
        ws = sum((rw * -n for rw, n in by[b] if n < 0), Fr(0))
        d = wl - (hbr or 0) * ws
        ds.append(d)
        buckets.append({"bucket": b, "wtd_long": f(wl), "wtd_short": f(ws), "drc": f(d)})
    return {"positions": scaled_rows(inp["positions"]), "hbr_ctp": None if hbr is None else f(hbr), "buckets": buckets,
            "drc": f(ctp_agg(ds)), "label": LABEL, "rw_source": RW_SOURCE}


def o_rrao(inp):
    rows, total = [], Fr(0)
    for x in inp["instruments"]:
        excl = x["back_to_back"] or (x["kind"] == "OTHER" and x["listed_or_clearable"])
        add = Fr(0) if excl else RRAO_W[x["kind"]] * Q(x["gross_notional"])
        total += add
        rows.append({"id": x["id"], "weight": f(RRAO_W[x["kind"]]), "excluded": excl, "addon": f(add)})
    return {"instruments": rows, "rrao": f(total), "label": LABEL}


def pos(pid, ob, bk, sen, n, mv, m, **kw):
    return {"id": pid, "obligor": ob, "bucket": bk, "seniority": sen, "notional": n, "market_value": mv, "maturity_years": m, **kw}


def gen_drc():
    s = Named("drc_k", SPEC_A, G)
    xl = pos("p1", "X", "CORPORATE", "SENIOR", 100, 100, 5)
    nonsec = "risk.frtb.drc_nonsec"

    def blind(cid, op, inp, oracle, desc, counted=True):
        out = oracle(inp)
        against_blind(cid, out)
        vb = ["hand (spec table, " + SPEC_A + ")", ORACLE,
              BLIND if counted else BLIND + ", but not blind: the stripped rules text states the answer (not counted)"]
        s.add_as(cid, op, inp, out, verified=vb, tags=TAGS_A + ["hand"], limit=LIMIT, description="hand: " + desc)

    blind("drc_k-0001", nonsec, {"positions": [xl], "ratings": {"X": "BBB"}}, o_nonsec, "one senior long, BBB")
    blind("drc_k-0002", nonsec, {"positions": [pos("p1", "X", "CORPORATE", "SENIOR", 100, 100, 0.5)], "ratings": {"X": "BBB"}},
          o_nonsec, "as 0001 with maturity one half (MAR22.15)")
    # drc_k-0003: MAR22.16 FAQ, printed 1/4*10 - 1/4*10 = 0 (EUR millions)
    inp3 = {"positions": [pos("future", "IDX", "CORPORATE", "EQUITY", -10000000, -10000000, 1 / 12),
                          pos("stock", "IDX", "CORPORATE", "EQUITY", 10000000, 10000000, 0.25, cash_equity=True)],
            "ratings": {"IDX": "BBB"}}
    o3 = o_nonsec(inp3)
    check(get(o3, "positions[future].scaled_jtd") == -2500000 and get(o3, "positions[stock].scaled_jtd") == 2500000
          and o3["obligors"][0]["net_long"] == 0 and o3["obligors"][0]["net_short"] == 0 and o3["drc"] == 0,
          "drc_k-0003 MAR22.16 FAQ (p.625): 1/4*10 - 1/4*10 = 0")
    s.add_as("drc_k-0003", nonsec, inp3, o3,
             verified=[ORACLE, "published: Basel Framework MAR22.16 FAQ, PDF p.625, printed '1/4*10 - 1/4*10 = 0': MATCH"],
             tags=TAGS_A + ["outside_checked", "published"], limit=LIMIT,
             description="MAR22.16 FAQ: short equity future (1 month, weight 0.25) against stock held 3 months; rating BBB is a choice (no effect)")
    blind("drc_k-0004", nonsec, {"positions": [xl, pos("p2", "X", "CORPORATE", "SENIOR", -100, -100, 0.25)], "ratings": {"X": "BBB"}},
          o_nonsec, "senior long 5y against a senior short of 3 months: offset after the maturity weight")
    blind("drc_k-0005", nonsec, {"positions": [pos("p1", "X", "CORPORATE", "SENIOR", 100, 80, 5), pos("p2", "Y", "CORPORATE", "SENIOR", -100, -80, 5)],
                                 "ratings": {"X": "A", "Y": "BB"}}, o_nonsec, "long A, short BB in one bucket: HBR 0.5, floored at 0")
    blind("drc_k-0006", nonsec, {"positions": [pos("p1", "X", "CORPORATE", "SENIOR", 100, 80, 5), pos("p2", "Y", "CORPORATE", "SENIOR", -100, -80, 5)],
                                 "ratings": {"X": "A", "Y": "AAA"}}, o_nonsec, "as 0005 with Y AAA")
    blind("drc_k-0007", nonsec, {"positions": [pos("stock", "Z", "CORPORATE", "EQUITY", 50, 50, 2, cash_equity=True),
                                               pos("bond", "Z", "CORPORATE", "SENIOR", -40, -40, 2)], "ratings": {"Z": "BB"}},
          o_nonsec, "worked example: a short senior bond does not offset a long stock (KR-53)")
    blind("drc_k-0008", nonsec, {"positions": [pos("bond", "Z", "CORPORATE", "SENIOR", 40, 40, 2),
                                               pos("stock", "Z", "CORPORATE", "EQUITY", -50, -50, 2, cash_equity=True)], "ratings": {"Z": "BB"}},
          o_nonsec, "a short stock offsets a long senior bond (KR-53)")
    blind("drc_k-0009", nonsec, {"positions": [pos("p1", "X", "CORPORATE", "SENIOR", 100, 100, 5), pos("p2", "S", "SOVEREIGN", "SENIOR", 200, 200, 5)],
                                 "ratings": {"X": "A", "S": "AA"}}, o_nonsec, "two buckets added (MAR22.26)")
    blind("drc_k-0010", nonsec, {"positions": [pos("sold_put", "X", "CORPORATE", "SENIOR", 100, 92, 5)], "ratings": {"X": "BBB"}},
          o_nonsec, "sold put mapped by MAR22.14 Table 1: notional 100, bond-equivalent value 92")
    blind("drc_k-0011", nonsec, {"positions": [pos("p1", "U", "CORPORATE", "SENIOR", 100, 100, 5),
                                               pos("p2", "D", "CORPORATE", "EQUITY", 5, 5, 2, cash_equity=True)],
                                 "ratings": {"U": "UNRATED", "D": "DEFAULTED"}}, o_nonsec, "unrated and defaulted risk weights")
    ctp = "risk.frtb.drc_ctp"
    o = o_ctp({"bucket_drc": [100, -100]})
    check(o["drc"] == 50, "ctp_k-0001 MAR22.45 (p.633): 100 - 0.5 x 100 = 50")
    s.add_as("ctp_k-0001", ctp, {"bucket_drc": [100, -100]}, o,
             verified=[ORACLE, "published: Basel Framework MAR22.45, PDF p.633, printed '100 - 0.5 x 100 = 50': MATCH"],
             tags=TAGS_A + ["outside_checked", "published"], limit=LIMIT, description="MAR22.45 printed example")
    blind("ctp_k-0002", ctp, {"positions": [
        {"id": "a", "index": "A", "series": "S1", "tranche": "T1", "market_value": 1000, "maturity_years": 5, "rw": 0.1},
        {"id": "b", "index": "B", "series": "S1", "tranche": "T1", "market_value": -1000, "maturity_years": 5, "rw": 0.1}]},
          o_ctp, "two indices: HBR over the whole CTP, a negative DRC_b at one half")
    blind("ctp_k-0003", ctp, {"bucket_drc": [-10]}, o_ctp, "a negative bucket alone floors at 0")
    blind("sec_k-0001", "risk.frtb.drc_sec_nonctp", {"positions": [
        {"id": "l", "bucket": "RMBS-EU", "pool": "P1", "tranche": "T1", "market_value": 50, "maturity_years": 5, "rw": 0.2},
        {"id": "s", "bucket": "RMBS-EU", "pool": "P1", "tranche": "T2", "market_value": -20, "maturity_years": 5, "rw": 0.2}]},
          o_sec, "different tranches of one pool do not offset (MAR22.29)")
    rr = "risk.frtb.rrao"

    def ins(i, g, k, lc=False, b2b=False):
        return {"id": i, "gross_notional": g, "kind": k, "listed_or_clearable": lc, "back_to_back": b2b}

    blind("rrao_k-0001", rr, {"instruments": [ins("e", 1000000, "EXOTIC"), ins("o", 2000000, "OTHER")]}, o_rrao, "1% and 0.1%")
    blind("rrao_k-0002", rr, {"instruments": [ins("o", 5000000, "OTHER", lc=True), ins("e1", 1000000, "EXOTIC", lc=True),
                                              ins("e2", 3000000, "EXOTIC", b2b=True)]}, o_rrao, "exclusions of MAR23.7")
    blind("rrao_k-0003", rr, {"instruments": []}, o_rrao, "empty list", counted=False)

    # ---- errors (order KR-67 = HR-122: E_SCHEMA, E_LIMIT, finite rule, structural E_INPUT, E_DOMAIN) ----
    n = {"a": 0}

    def err(prefix, op, inp, code, desc):
        n[prefix] = n.get(prefix, 0) + 1
        s.add_as(f"{prefix}-{n[prefix]:04d}", op, inp, error=code, cls="date_and_convention", verified=["hand"],
                 tags=TAGS_A + ["error"], description="hand: " + desc)

    ok = pos("p1", "X", "CORPORATE", "SENIOR", 100, 100, 5)
    R = {"X": "BBB"}
    nn = {k: v for k, v in ok.items() if k != "notional"}
    err("drc_ke", nonsec, {"positions": [nn], "ratings": R}, "E_SCHEMA", "notional missing")
    err("drc_ke", nonsec, {"positions": [{**ok, "seniority": "JUNIOR"}], "ratings": R}, "E_SCHEMA", "seniority JUNIOR is not listed")
    err("drc_ke", nonsec, {"positions": [ok], "ratings": {"Y": "BBB"}}, "E_INPUT", "obligor without a rating")
    err("drc_ke", nonsec, {"positions": [{**ok, "maturity_years": 0}], "ratings": R}, "E_DOMAIN", "maturity 0")
    err("drc_ke", nonsec, {"positions": [pos("s", "X", "CORPORATE", "EQUITY", 5, 5, 0.5, cash_equity=True)], "ratings": R}, "E_DOMAIN",
        "cash equity maturity 0.5 (KR-52)")
    err("drc_ke", nonsec, {"positions": [{**nn, "maturity_years": 0}], "ratings": R}, "E_SCHEMA", "two errors: notional missing and maturity 0 [schema] [domain]")
    err("drc_ke", nonsec, {"positions": [ok], "ratings": {"X": "BAA"}}, "E_SCHEMA", "rating BAA is not listed")
    err("drc_ke", nonsec, {"positions": [{**ok, "bucket": "MUNICIPAL"}], "ratings": R}, "E_SCHEMA", "bucket not listed")
    err("drc_ke", nonsec, {"positions": {"p1": ok}, "ratings": R}, "E_SCHEMA", "positions not an array")
    err("drc_ke", nonsec, {"positions": [{**ok, "notional": "100"}], "ratings": R}, "E_SCHEMA", "notional a string")
    err("drc_ke", nonsec, {"positions": [], "ratings": R}, "E_INPUT", "no positions")
    err("drc_ke", nonsec, {"positions": [ok, ok], "ratings": R}, "E_INPUT", "duplicate id")
    err("drc_ke", nonsec, {"positions": [ok, {**ok, "id": "p2", "bucket": "SOVEREIGN"}], "ratings": R}, "E_INPUT",
        "one obligor in two buckets (KR-301)")
    err("drc_ke", nonsec, {"positions": [{**ok, "notional": 0, "market_value": 5}], "ratings": R}, "E_DOMAIN", "zero notional, nonzero value")
    err("drc_ke", nonsec, {"positions": [{**ok, "cash_equity": True, "maturity_years": 1}], "ratings": R}, "E_DOMAIN",
        "cash equity flagged on a senior bond (KR-300)")
    err("drc_ke", nonsec, {"positions": [pos("s", "X", "CORPORATE", "EQUITY", 5, 6, 1, cash_equity=True)], "ratings": R}, "E_DOMAIN",
        "cash equity with notional not equal to market value (KR-300)")
    err("drc_ke", nonsec, {"positions": [{**ok, "market_value": "NaN"}], "ratings": R}, "E_DOMAIN", "E1: market value NaN")
    err("drc_ke", nonsec, {"positions": [{**ok, "notional": "Infinity"}], "ratings": {"Y": "A"}}, "E_DOMAIN",
        "E1, two errors: notional Infinity and obligor without a rating (the finite rule first) [finite] [structural]")
    err("drc_ke", nonsec, {"positions": [ok, {**ok, "maturity_years": -1}], "ratings": R}, "E_INPUT", "two errors: duplicate id and maturity -1 [structural] [domain]")
    err("drc_ke", nonsec, {"positions": [{**ok, "cash_equity": "yes"}], "ratings": R}, "E_SCHEMA", "cash_equity not a boolean")
    sp = {"id": "l", "bucket": "RMBS-EU", "pool": "P1", "tranche": "T1", "market_value": 50, "maturity_years": 5, "rw": 0.2}
    sec = "risk.frtb.drc_sec_nonctp"
    err("sec_ke", sec, {"positions": [{k: v for k, v in sp.items() if k != "rw"}]}, "E_SCHEMA", "rw missing")
    err("sec_ke", sec, {"positions": [{**sp, "rw": 13}]}, "E_DOMAIN", "rw above 12.5")
    err("sec_ke", sec, {"positions": [{**sp, "rw": -0.1}]}, "E_DOMAIN", "negative rw")
    err("sec_ke", sec, {"positions": [{**sp, "maturity_years": 0}]}, "E_DOMAIN", "maturity 0")
    err("sec_ke", sec, {"positions": [sp, sp]}, "E_INPUT", "duplicate id")
    err("sec_ke", sec, {"positions": [sp, {**sp, "id": "m", "rw": 0.3}]}, "E_INPUT", "one pool and tranche with two rw (KR-303)")
    err("sec_ke", sec, {"positions": [{**sp, "rw": "NaN"}]}, "E_DOMAIN", "E1: rw NaN")
    err("sec_ke", sec, {"positions": [sp, {**sp, "rw": 13}]}, "E_INPUT", "two errors: duplicate id and rw above 12.5 [structural] [domain]")
    cp = {"id": "a", "index": "A", "series": "S1", "tranche": "T1", "market_value": 1000, "maturity_years": 5, "rw": 0.1}
    err("ctp_ke", ctp, {"positions": [cp], "bucket_drc": [1]}, "E_INPUT", "both positions and bucket_drc")
    err("ctp_ke", ctp, {}, "E_INPUT", "neither positions nor bucket_drc")
    err("ctp_ke", ctp, {"bucket_drc": [1, "x"]}, "E_SCHEMA", "bucket_drc holds a string")
    err("ctp_ke", ctp, {"positions": [{**cp, "rw": 20}]}, "E_DOMAIN", "rw above 12.5")
    err("ctp_ke", ctp, {"positions": [{**cp, "maturity_years": -1}]}, "E_DOMAIN", "negative maturity")
    err("ctp_ke", ctp, {"positions": [cp, {**cp, "id": "b", "rw": 0.2}]}, "E_INPUT", "one index, series and tranche with two rw (KR-303)")
    err("ctp_ke", ctp, {"bucket_drc": ["NaN"]}, "E_DOMAIN", "E1: bucket_drc NaN")
    err("ctp_ke", ctp, {"positions": [cp], "bucket_drc": ["-Infinity"]}, "E_DOMAIN",
        "E1, two errors: bucket_drc -Infinity and both inputs given (the finite rule first) [finite] [structural]")
    ie = ins("e", 100, "EXOTIC")
    err("rrao_ke", rr, {"instruments": [{**ie, "gross_notional": -1}]}, "E_DOMAIN", "negative gross notional")
    err("rrao_ke", rr, {"instruments": [{**ie, "kind": "WEATHER"}]}, "E_SCHEMA", "kind not listed")
    err("rrao_ke", rr, {"instruments": [{k: v for k, v in ie.items() if k != "back_to_back"}]}, "E_SCHEMA", "back_to_back missing")
    err("rrao_ke", rr, {"instruments": [ie, ie]}, "E_INPUT", "duplicate id")
    err("rrao_ke", rr, {"instruments": [{**ie, "gross_notional": "NaN"}]}, "E_DOMAIN", "E1: gross notional NaN")
    err("rrao_ke", rr, {"instruments": [ie, {**ie, "gross_notional": -1}]}, "E_INPUT", "two errors: duplicate id and negative notional [structural] [domain]")
    err("rrao_ke", rr, {"instruments": [{**ie, "kind": "WEATHER", "gross_notional": -1}]}, "E_SCHEMA", "two errors: kind not listed and negative notional [schema] [domain]")
    s.write()
    return s


# ---- K-8f oracle (MAR31, MAR32, MAR33) --------------------------------------------------------------------
LH = [int(entry("mar33_ima", "lh.j")[str(j)]) for j in range(1, 6)]
T_BASE = int(entry("mar33_ima", "es.base_horizon_days"))
C975 = Fr(entry("mar33_ima", "es.confidence"))
LH_TABLE = entry("mar33_ima", "lh.table")
PAIRS = [tuple(p.split("/")) for p in entry("mar33_ima", "lh.specified_fx_pairs")]
MULT = entry("mar32_pla", "backtest.zone_multiplier")
SES_RHO = mp.mpf(entry("mar33_ima", "ses.rho"))
IMCC_RHO = Fr(entry("mar33_ima", "imcc.rho"))
GREEN_RS, RED_RS = Fr(entry("mar32_pla", "pla.green.spearman_above")), Fr(entry("mar32_pla", "pla.red.spearman_below"))
GREEN_KS, RED_KS = Fr(entry("mar32_pla", "pla.green.ks_below")), Fr(entry("mar32_pla", "pla.red.ks_above"))


def avg_ranks(x):
    """Average rank of each value: (first position + last position) / 2, positions from 1."""
    srt = sorted(x)
    first, cnt = {}, Counter(srt)
    for k, v in enumerate(srt):
        first.setdefault(v, k)
    return [Fr(2 * first[v] + cnt[v] + 1, 2) for v in x]


def o_pla(hpl, rtpl):
    n = len(hpl)
    a, b = avg_ranks(hpl), avg_ranks(rtpl)
    ma, mb = sum(a) / n, sum(b) / n
    sxy = sum((u - ma) * (v - mb) for u, v in zip(a, b))
    sxx, syy = sum((u - ma) ** 2 for u in a), sum((v - mb) ** 2 for v in b)
    rs = mp.mpf(sxy.numerator) / sxy.denominator / mp.sqrt(mp.mpf(sxx.numerator) / sxx.denominator * mp.mpf(syy.numerator) / syy.denominator)
    pooled = sorted(set(hpl) | set(rtpl))
    d = max(abs(sum(1 for v in rtpl if v <= x) - sum(1 for v in hpl if v <= x)) for x in pooled)
    ks = Fr(d, n)
    zone = ("GREEN" if rs > GREEN_RS and ks < GREEN_KS else "RED" if rs < RED_RS or ks > RED_KS else "AMBER")
    return {"n": n, "spearman": f(rs), "ks": f(ks), "ks_count": d, "zone": zone,
            "ks_pvalue_asymptotic": f(q_ks(mp.mpf(ks.numerator) / ks.denominator * mp.sqrt(mp.mpf(n) / 2))),
            "regulatory_window": n == int(entry("mar32_pla", "pla.window_days")), "label": LABEL}


def q_ks(x):
    """Kolmogorov tail by the defining series, summed to 4,000 terms at 50 digits (KR-56)."""
    if x == 0:
        return mp.mpf(1)
    return 2 * mp.fsum((-1) ** (k - 1) * mp.exp(-2 * k * k * x * x) for k in range(1, 4001))


def es_hist(pnl):
    """var-es-and-backtests.md: tail weight w = n - n c, the floor(w) largest losses and the next at w - m."""
    losses = sorted((-Fr(v) for v in pnl), reverse=True)
    n = len(losses)
    w = n - n * C975
    m = math.floor(w)
    return (sum(losses[:m], Fr(0)) + (w - m) * losses[m]) / w


def cascade(es):
    w = [Fr(1)] + [Fr(LH[j] - LH[j - 1], T_BASE) for j in range(1, 5)]
    return mp.sqrt(mp.fsum(mp.mpf(x.numerator) / x.denominator * mp.mpf(e) ** 2 for x, e in zip(w, es)))


def normal_factor():
    z = mp.sqrt(2) * mp.erfinv(2 * mp.mpf("0.975") - 1)
    return mp.npdf(z) / (1 - mp.mpf("0.975"))


def o_es(inp):
    if "es_t" in inp:
        es = [mp.mpf(v) for v in inp["es_t"]]
        mode = "es_t"
    elif "sigma" in inp:
        es = [normal_factor() * v for v in inp["sigma"]]
        mode = "sigma"
    else:
        es = [mp.mpf(es_hist(l).numerator) / es_hist(l).denominator if l else mp.mpf(0) for l in inp["pnl"]]
        mode = "pnl"
    return {"mode": mode, "es_by_horizon": [f(e) for e in es], "es": f(cascade(es)), "label": LABEL}


def stressed(rs, fc, rc):
    r = Fr(fc) / Fr(rc)
    return r, r < 1, Fr(rs) * max(Fr(1), r)


def o_est(inp):
    r, fl, es = stressed(inp["es_rs"], inp["es_fc"], inp["es_rc"])
    return {"ratio": f(r), "ratio_floored": fl, "es": f(es), "label": LABEL}


def o_imcc(inp):
    p = inp["portfolio"]
    _, pf, whole = stressed(p["es_rs"], p["es_fc"], p["es_rc"])
    per = {c: stressed(t["es_rs"], t["es_fc"], t["es_rc"]) for c, t in inp["classes"].items()}
    total = IMCC_RHO * whole + (1 - IMCC_RHO) * sum((v[2] for v in per.values()), Fr(0))
    order = ["IR", "EQ", "FX", "COM", "CS"]
    return {"imcc_c": f(whole), "portfolio_floored": pf, "classes": {c: f(per[c][2]) for c in order if c in per},
            "classes_floored": [c for c in order if c in per and per[c][1]], "imcc": f(total), "label": LABEL}


def o_ses(inp):
    a = mp.sqrt(mp.fsum(mp.mpf(v) ** 2 for v in inp["idio_credit"]))
    b = mp.sqrt(mp.fsum(mp.mpf(v) ** 2 for v in inp["idio_equity"]))
    o = [mp.mpf(v) for v in inp["other"]]
    c = mp.sqrt((SES_RHO * mp.fsum(o)) ** 2 + (1 - SES_RHO ** 2) * mp.fsum(v * v for v in o))
    return {"idio_credit": f(a), "idio_equity": f(b), "other": f(c), "ses": f(a + b + c), "label": LABEL}


def o_cap(inp):
    x = inp["exceptions"]
    m = Fr(MULT[str(x)] if x < 10 else MULT["10+"]) + Fr(inp.get("qualitative_addon", 0))
    ca = max(Fr(inp["imcc_prev"]) + Fr(inp["ses_prev"]), m * Fr(inp["imcc_avg"]) + Fr(inp["ses_avg"]))
    ga = ca + Fr(inp["drc"])
    sa = sum((Fr(d["sa"]) for d in inp["desks"]), Fr(0))
    amber = sum((Fr(d["sa"]) for d in inp["desks"] if d["zone"] == "AMBER"), Fr(0))
    k = Fr(1, 2) * amber / sa if any(d["zone"] == "AMBER" for d in inp["desks"]) else Fr(0)
    sur = k * max(Fr(0), sa - ga)
    acr = min(ga + sur + Fr(inp["c_u"]), Fr(inp["sa_all"])) + max(Fr(0), ga - sa)
    return {"m_c": f(m), "c_a": f(ca), "ima_ga": f(ga), "sa_ga": f(sa), "k": f(k), "surcharge": f(sur), "acr_total": f(acr), "label": LABEL}


def o_rfet(inp):
    asof = date.fromisoformat(inp["as_of"])
    y, mth = (asof.year - 1, asof.month)
    last_day = (date(y + (mth == 12), mth % 12 + 1, 1) - timedelta(days=1)).day
    start = date(y, mth, min(asof.day, last_day)) + timedelta(days=1)
    days = {date.fromisoformat(d) for d in inp["observations"]}
    days = {d for d in days if start <= d <= asof}
    counts = []
    s = start
    while s + timedelta(days=89) <= asof:
        counts.append((s, sum(1 for d in days if s <= d <= s + timedelta(days=89))))
        s += timedelta(days=1)
    bad = next(((s, c) for s, c in counts if c < 4), None)
    c1 = len(days) >= 24 and bad is None
    c2 = len(days) >= 100
    return {"window_start": start.isoformat(), "distinct_days": len(days), "min_window_count": min(c for _, c in counts),
            "first_failing_window_start": None if bad is None else bad[0].isoformat(),
            "first_failing_window_count": None if bad is None else bad[1], "crit1": c1, "crit2": c2, "pass": c1 or c2, "label": LABEL}


def o_bucket(inp):
    row = inp["row"]
    rows = entry("mar31_rfet", "bucket." + row)
    x = Fr(str(inp["delta"] if row == "D" else inp["t"]))
    for k, (lo, hi) in enumerate(rows):
        if Fr(lo) <= x and (hi == "inf" or x < Fr(hi)):
            return {"bucket": k + 1, "lower": f(Fr(lo)), "upper": None if hi == "inf" else f(Fr(hi)), "label": LABEL}
    raise SystemExit("no bucket")


def o_lh(inp):
    five = LH

    def up(x):
        return next((h for h in five if h >= x), five[-1])

    if "category" in inp:
        base, rule = LH_TABLE[inp["category"]], "table"
    elif "fx_pair" in inp:
        a, b = inp["fx_pair"].split("/")
        listed = {frozenset(p) for p in PAIRS}
        ccys = {c for p in PAIRS for c in p}
        spec = frozenset((a, b)) in listed or any(frozenset((a, c)) in listed and frozenset((b, c)) in listed for c in ccys)
        base, rule = (LH_TABLE["FX_specified_pairs"] if spec else LH_TABLE["FX_pairs"]), "fx_pair"
    else:
        wavg = sum((Fr(str(c["weight"])) * c["n"] for c in inp["constituents"]), Fr(0))
        base, rule = up(wavg), "index"
    n = base
    if "maturity_days" in inp and Fr(str(inp["maturity_days"])) < base:
        n, rule = up(Fr(str(inp["maturity_days"]))), rule + "+maturity"
    return {"n": n, "table_n": base, "rule": rule, "label": LABEL}


def h_series():
    return [((7919 * t + 13) % 1009) - 504 for t in range(250)]


def rtpl(kind):
    h = h_series()
    return {"A": [h[t] + ((37 * t) % 101) - 50 for t in range(250)],
            "B": [h[t] + 4 * (((53 * t) % 211) - 105) for t in range(250)],
            "C": [2 * h[t] + 300 for t in range(250)],
            "D": [((433 * t + 7) % 1009) - 504 for t in range(250)],
            "E": [h[t] + 6 * (((53 * t) % 211) - 105) for t in range(250)]}[kind]


def days(a, b):
    d0, d1 = date.fromisoformat(a), date.fromisoformat(b)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def every15(k=24):
    return [(date(2025, 7, 5) + timedelta(days=15 * i)).isoformat() for i in range(k)]


def gen_ima():
    s = Named("ima_k", SPEC_F, G)
    s.compact = False
    pla, pv = "risk.frtb.pla", "risk.frtb.pla.ks_pvalue"
    sp = "scipy " + __import__("scipy").__version__

    # PLA value cases: spec values (printed in frtb-ima.md), SciPy spearmanr / ks_2samp / kstwobign
    pla_spec = {"pla_k-0002": ("A", "0.994739210447638", 9, "GREEN"), "pla_k-0003": ("B", "0.767250804012864", 30, "AMBER"),
                "pla_k-0004": ("C", "1", 99, "RED"), "pla_k-0005": ("D", "0.0098585897374358", 2, "RED"),
                "pla_k-0006": ("E", "0.650419238707819", 49, "RED")}
    hp, rp = [-3, 1, 4, -1, 2], [-2, 0, 5, 1, 3]
    o = o_pla(hp, rp)
    check(close(o["spearman"], 0.9) and o["ks_count"] == 1 and close(o["ks"], 0.2) and o["zone"] == "RED", "pla_k-0001 spec values")
    cases = [("pla_k-0001", hp, rp, o, "five-day worked example: ranks agree well, KS 0.2 is red")]
    for cid, (kind, rs_txt, d, zone) in pla_spec.items():
        r = rtpl(kind)
        o = o_pla(h_series(), r)
        check(printed(o["spearman"], rs_txt) and o["ks_count"] == d and o["zone"] == zone, f"{cid} spec values spearman {rs_txt}, d {d}, {zone}")
        cases.append((cid, h_series(), r, o, f"HPL h, RTPL {kind} (frtb-ima.md series)"))
    check(printed(cases[2][3]["ks_pvalue_asymptotic"], "0.0546463301139"), "pla_k-0003 p-value 0.0546463301139")
    for cid, hpl, rt, o, desc in cases:
        sr = float(stats.spearmanr(hpl, rt).statistic)
        kr = float(stats.ks_2samp(hpl, rt).statistic)
        pr = float(stats.kstwobign.sf(o["ks"] * math.sqrt(len(hpl) / 2)))
        check(abs(sr - o["spearman"]) <= 1e-12 and abs(kr - o["ks"]) <= 1e-12 and abs(pr - o["ks_pvalue_asymptotic"]) <= 1e-12,
              f"{cid} SciPy spearmanr {sr!r}, ks_2samp {kr!r}, kstwobign.sf {pr!r}")
        s.add_as(cid, pla, {"hpl": hpl, "rtpl": rt}, o,
                 verified=["hand (spec table, " + SPEC_F + ")", ORACLE,
                           f"{sp} stats.spearmanr, stats.ks_2samp, stats.kstwobign.sf (independent library): MATCH 1e-12; " + NOT_COUNTED_SCIPY, BLIND_IMA2],
                 tags=TAGS_F + ["library_checked"], limit=LIMIT, description=desc)
    for cid, ks, val, prn in (("pla_k-0007", 0.09, "0.263380632422", "0.264"), ("pla_k-0008", 0.12, "0.0546463301139", "0.055")):
        # the input ks is the binary64 0.09 / 0.12, so the oracle evaluates at that value
        q = q_ks(mp.mpf(ks) * mp.sqrt(mp.mpf(125)))
        check(printed(f(q), val), f"{cid} spec value {val}")
        check(abs(f(q) - float(prn)) <= 1e-3, f"{cid} MAR32.42 (p.667) printed p-value {prn} within 1e-3")
        sc = float(stats.kstwobign.sf(ks * math.sqrt(125)))
        check(abs(sc - f(q)) <= 1e-12, f"{cid} SciPy kstwobign.sf {sc!r}")
        s.add_as(cid, pv, {"ks": ks, "n": 250}, {"pvalue": f(q), "label": LABEL},
                 verified=[ORACLE, f"published: Basel Framework MAR32.42, PDF p.667, printed p-value {prn}: MATCH within 1e-3 (tolerance fixed in the spec before any run; the asymptotic value is {val})",
                           f"{sp} stats.kstwobign.sf (independent library): MATCH 1e-12; " + NOT_COUNTED_SCIPY],
                 tags=TAGS_F + ["outside_checked", "published"], limit=LIMIT, description=f"Kolmogorov tail at KS {ks}, n 250 (MAR32.42)")

    def blind(cid, op, inp, oracle, desc):
        out = oracle(inp)
        against_blind(cid, out)
        s.add_as(cid, op, inp, out, verified=["hand (spec table, " + SPEC_F + ")", ORACLE, BLIND], tags=TAGS_F + ["hand"],
                 limit=LIMIT, description="hand: " + desc)

    es = "risk.frtb.ima.es_lh"
    for cid, sig, val, scale in (("es_k-0001", [1, 0, 0, 0, 0], "2.337802792201415", 1.0), ("es_k-0002", [1, 1, 1, 1, 1], "8.098386428338474", math.sqrt(12))):
        o = o_es({"sigma": sig})
        check(printed(o["es"], val), f"{cid} spec value {val}")
        z = float(stats.norm.ppf(0.975))
        qv = integrate.quad(lambda x: x * stats.norm.pdf(x), z, math.inf, epsabs=1e-15, epsrel=1e-14)[0] / 0.025 * scale
        check(abs(qv - o["es"]) <= 1e-12 * o["es"], f"{cid} SciPy quad of the normal tail {qv!r}")
        s.add_as(cid, es, {"sigma": sig}, o,
                 verified=["hand (spec table, " + SPEC_F + ")", ORACLE,
                           f"{sp} integrate.quad of the normal tail (independent library, a different formulation): MATCH 1e-12; not counted here: whether D6 classes it library-primitive is the coordinator's decision", BLIND_IMA2],
                 tags=TAGS_F + ["library_checked"], limit=LIMIT, description="normal mode (KR-57)")
    blind("es_k-0003", es, {"es_t": [10, 8, 6, 4, 2]}, o_es, "liquidity-horizon cascade, weights 1, 1, 2, 2, 6")
    blind("es_k-0004", es, {"es_t": [10, 0, 0, 0, 0]}, o_es, "only the 10-day horizon")
    blind("es_k-0005", es, {"pnl": [h_series(), [], [], [], []]}, o_es, "historical ES of the h series; empty lists give 0")
    est = "risk.frtb.ima.es_stressed"
    blind("est_k-0001", est, {"es_rs": 12, "es_fc": 10, "es_rc": 8}, o_est, "ratio 1.25")
    blind("est_k-0002", est, {"es_rs": 12, "es_fc": 7, "es_rc": 8}, o_est, "ratio below 1 floored (KR-58)")
    blind("imcc_k-0001", "risk.frtb.ima.imcc", {"portfolio": {"es_rs": 12, "es_fc": 10, "es_rc": 8},
                                                "classes": {"IR": {"es_rs": 6, "es_fc": 5, "es_rc": 4}, "EQ": {"es_rs": 5, "es_fc": 4, "es_rc": 5}}},
          o_imcc, "IMCC with two risk classes, EQ floored")
    ses = "risk.frtb.ima.ses"
    blind("ses_k-0001", ses, {"idio_credit": [3, 4], "idio_equity": [5, 12], "other": [1, 2, 2]}, o_ses, "worked example")
    blind("ses_k-0002", ses, {"idio_credit": [], "idio_equity": [], "other": [10]}, o_ses, "one other charge")
    cap = "risk.frtb.ima.capital"
    base = {"imcc_prev": 100, "ses_prev": 20, "imcc_avg": 90, "ses_avg": 15, "exceptions": 6, "qualitative_addon": 0}
    blind("cap_k-0001", cap, {**base, "drc": 0, "desks": [{"zone": "GREEN", "sa": 200}], "c_u": 0, "sa_all": 1000}, o_cap,
          "six exceptions: m_c 1.76 (MAR32.9 lookup); C_A")
    blind("cap_k-0002", cap, {**base, "drc": 30, "desks": [{"zone": "GREEN", "sa": 150}, {"zone": "AMBER", "sa": 100}], "c_u": 40, "sa_all": 300},
          o_cap, "worked example with an amber desk surcharge")
    blind("cap_k-0003", cap, {**base, "drc": 30, "desks": [{"zone": "GREEN", "sa": 180}], "c_u": 40, "sa_all": 220}, o_cap,
          "no amber desk; ACR capped by the SA of all desks plus the IMA excess")
    rf = "risk.frtb.rfet"
    blind("rfet_k-0001", rf, {"as_of": "2026-06-30", "observations": days("2026-03-23", "2026-06-30")}, o_rfet, "100 days, all in the last quarter")
    blind("rfet_k-0002", rf, {"as_of": "2026-06-30", "observations": every15()}, o_rfet, "24 days, every 15 days")
    blind("rfet_k-0003", rf, {"as_of": "2026-06-30", "observations": days("2025-07-01", "2025-07-30")}, o_rfet, "30 days in the first month")
    blind("rfet_k-0004", rf, {"as_of": "2026-06-30", "observations": [d for d in every15(23) for _ in (0, 1)]}, o_rfet,
          "23 days, each listed twice")
    bk = "risk.frtb.rfet.bucket"
    for cid, inp, val in (("rfet_k-0005", {"row": "A", "t": 0.75}, 2), ("rfet_k-0006", {"row": "C", "t": 7.5}, 4),
                          ("rfet_k-0007", {"row": "D", "delta": 0.95}, 5), ("rfet_k-0008", {"row": "B", "t": 30}, 6)):
        o = o_bucket(inp)
        check(o["bucket"] == val, f"{cid} spec value {val}")
        s.add_as(cid, bk, inp, o, verified=[ORACLE, "table lookup: MAR31.16 Table 1, PDF p.652 (T, not counted under KR-68)"],
                 tags=TAGS_F + ["table_lookup"], limit=LIMIT, description="MAR31.16 Table 1 bucket, lower bound inclusive")
    lh = "risk.frtb.ima.lh"
    for cid, inp, val, src in (
            ("lh_k-0001", {"category": "IR_volatility", "maturity_days": 30}, 40,
             "published: Basel Framework MAR33.12 FAQ4, PDF p.675, printed example (30-day maturity, 60-day category): 40: MATCH"),
            ("lh_k-0002", {"constituents": [{"weight": 0.8, "n": 10}, {"weight": 0.2, "n": 20}]}, 20,
             "published: Basel Framework MAR33.12 FAQ5, PDF p.675, printed example (weighted 12): 20: MATCH"),
            ("lh_k-0003", {"fx_pair": "JPY/USD"}, 10, "table lookup: MAR33.12 footnote 309, PDF p.675 (T, not counted under KR-68)"),
            ("lh_k-0004", {"category": "CS_corporate_HY"}, 60, "table lookup: MAR33.12 Table 2, PDF p.674 (T, not counted under KR-68)")):
        o = o_lh(inp)
        check(o["n"] == val, f"{cid} spec value {val}" + (" (printed)" if src.startswith("published") else ""))
        pub = src.startswith("published")
        s.add_as(cid, lh, inp, o, verified=[ORACLE, src], tags=TAGS_F + (["outside_checked", "published"] if pub else ["table_lookup"]),
                 limit=LIMIT, description="liquidity horizon (MAR33.12, KR-60)")

    # ---- errors ----
    n = {}

    def err(prefix, op, inp, code, desc):
        n[prefix] = n.get(prefix, 0) + 1
        s.add_as(f"{prefix}-{n[prefix]:04d}", op, inp, error=code, cls="date_and_convention", verified=["hand"],
                 tags=TAGS_F + ["error"], description="hand: " + desc)

    h = h_series()
    err("pla_ke", pla, {"hpl": h, "rtpl": rtpl("A")[:249]}, "E_INPUT", "lengths 250 and 249")
    err("pla_ke", pla, {"hpl": hp, "rtpl": [1, 1, 1, 1, 1]}, "E_DOMAIN", "constant RTPL")
    err("pla_ke", pla, {"hpl": [1, 2], "rtpl": [2, 1]}, "E_DOMAIN", "two observations (KR-56: at least 3)")
    err("pla_ke", pla, {"hpl": [1, "2", 3], "rtpl": [1, 2, 3]}, "E_SCHEMA", "hpl holds a string")
    err("pla_ke", pla, {"hpl": [1, 2, 3]}, "E_SCHEMA", "rtpl missing")
    err("pla_ke", pla, {"hpl": [1, "NaN", 3], "rtpl": [1, 2, 3]}, "E_DOMAIN", "E1: hpl NaN")
    err("pla_ke", pla, {"hpl": [1, 2, 3, 4], "rtpl": [5, 5, 5]}, "E_INPUT", "two errors: lengths differ and a constant RTPL [structural] [domain]")
    err("pla_ke", pla, {"hpl": [1, 2, "Infinity"], "rtpl": [1, 2]}, "E_DOMAIN", "E1, two errors: hpl Infinity and lengths differ (the finite rule first) [finite] [structural]")
    err("pla_ke", pv, {"ks": 1.5, "n": 250}, "E_DOMAIN", "ks above 1")
    err("pla_ke", pv, {"ks": 0.1, "n": 0}, "E_DOMAIN", "n 0 (KR-305)")
    err("pla_ke", pv, {"ks": 0.1, "n": 2.5}, "E_SCHEMA", "n not an integer")
    err("pla_ke", pv, {"ks": "NaN", "n": 250}, "E_DOMAIN", "E1: ks NaN")
    err("pla_ke", pv, {"ks": -0.5, "n": "x"}, "E_SCHEMA", "two errors: n a string and ks negative [schema] [domain]")
    err("es_ke", es, {"es_t": [10, -1, 0, 0, 0]}, "E_DOMAIN", "negative ES")
    err("es_ke", es, {"es_t": [10, -1, 0, 0]}, "E_INPUT", "two errors: four horizons and a negative ES [structural] [domain]")
    err("es_ke", es, {"es_t": [1, 0, 0, 0, 0], "sigma": [1, 0, 0, 0, 0]}, "E_INPUT", "es_t and sigma both given")
    err("es_ke", es, {}, "E_INPUT", "none of es_t, sigma, pnl")
    err("es_ke", es, {"sigma": [1, 0, -2, 0, 0]}, "E_DOMAIN", "negative sigma")
    err("es_ke", es, {"pnl": [[1, 2, 3], [], [], [], []]}, "E_DOMAIN", "a P&L list of gains only: negative ES (KR-307)")
    err("es_ke", es, {"pnl": [[1, "x"], [], [], [], []]}, "E_SCHEMA", "a P&L entry that is a string")
    err("es_ke", es, {"es_t": [10, "NaN", 0, 0, 0]}, "E_DOMAIN", "E1: es_t NaN")
    err("es_ke", es, {"es_t": ["NaN", 0, 0, 0]}, "E_DOMAIN", "E1, two errors: es_t NaN and four horizons (the finite rule first) [finite] [structural]")
    err("est_ke", est, {"es_rs": 12, "es_fc": 10, "es_rc": 0}, "E_DOMAIN", "ES_R,C 0")
    err("est_ke", est, {"es_rs": -1, "es_fc": 10, "es_rc": 8}, "E_DOMAIN", "negative ES_R,S")
    err("est_ke", est, {"es_rs": 12, "es_rc": 8}, "E_SCHEMA", "es_fc missing")
    err("est_ke", est, {"es_rs": 12, "es_fc": "NaN", "es_rc": 8}, "E_DOMAIN", "E1: es_fc NaN")
    err("est_ke", est, {"es_rs": 12, "es_rc": 0}, "E_SCHEMA", "two errors: es_fc missing and ES_R,C 0 [schema] [domain]")
    im = "risk.frtb.ima.imcc"
    tri = {"es_rs": 12, "es_fc": 10, "es_rc": 8}
    err("imcc_ke", im, {"portfolio": tri, "classes": {"RATES": tri}}, "E_SCHEMA", "class RATES not listed")
    err("imcc_ke", im, {"portfolio": tri, "classes": {}}, "E_INPUT", "no risk class")
    err("imcc_ke", im, {"portfolio": tri, "classes": {"IR": {**tri, "es_rc": 0}}}, "E_DOMAIN", "a class ES_R,C 0")
    err("imcc_ke", im, {"portfolio": tri, "classes": {"IR": {**tri, "es_rs": "NaN"}}}, "E_DOMAIN", "E1: a class ES NaN")
    err("imcc_ke", im, {"portfolio": {**tri, "es_rc": 0}, "classes": {}}, "E_INPUT", "two errors: no risk class and portfolio ES_R,C 0 [structural] [domain]")
    err("ses_ke", ses, {"idio_credit": [1, -2], "idio_equity": [], "other": []}, "E_DOMAIN", "negative charge")
    err("ses_ke", ses, {"idio_credit": [], "idio_equity": []}, "E_SCHEMA", "other missing")
    err("ses_ke", ses, {"idio_credit": [], "idio_equity": ["NaN"], "other": []}, "E_DOMAIN", "E1: a charge NaN")
    err("ses_ke", ses, {"idio_credit": [-1], "idio_equity": []}, "E_SCHEMA", "two errors: other missing and a negative charge [schema] [domain]")
    full = {**base, "drc": 30, "desks": [{"zone": "GREEN", "sa": 150}, {"zone": "AMBER", "sa": 100}], "c_u": 40, "sa_all": 300}
    err("cap_ke", cap, {**full, "exceptions": -1}, "E_DOMAIN", "exceptions -1")
    err("cap_ke", cap, {**full, "desks": [{"zone": "RED", "sa": 1}]}, "E_SCHEMA", "desk zone RED is not listed")
    err("cap_ke", cap, {**full, "desks": [{"zone": "AMBER", "sa": 0}]}, "E_DOMAIN", "SA sum 0 with an amber desk")
    err("cap_ke", cap, {**full, "drc": -1}, "E_DOMAIN", "negative DRC (KR-308)")
    err("cap_ke", cap, {**full, "desks": [{"zone": "GREEN", "sa": -5}]}, "E_DOMAIN", "negative desk SA (KR-308)")
    err("cap_ke", cap, {**full, "exceptions": 1.5}, "E_SCHEMA", "exceptions not an integer")
    err("cap_ke", cap, {**full, "imcc_avg": "NaN"}, "E_DOMAIN", "E1: imcc_avg NaN")
    err("cap_ke", cap, {**full, "desks": [{"zone": "RED", "sa": 1}], "exceptions": -1}, "E_SCHEMA", "two errors: zone RED and exceptions -1 [schema] [domain]")
    err("rfet_ke", bk, {"row": "D", "delta": 1}, "E_DOMAIN", "delta 1 (KR-59)")
    err("rfet_ke", bk, {"row": "E", "t": 1}, "E_SCHEMA", "row E is not listed")
    err("rfet_ke", bk, {"row": "A", "delta": 0.5}, "E_INPUT", "row A with a delta (KR-309)")
    err("rfet_ke", bk, {"row": "D", "t": 0.5}, "E_INPUT", "row D with a maturity (KR-309)")
    err("rfet_ke", bk, {"row": "B", "t": -1}, "E_DOMAIN", "negative maturity")
    err("rfet_ke", bk, {"row": "C", "t": "NaN"}, "E_DOMAIN", "E1: t NaN")
    err("rfet_ke", bk, {"row": "A", "t": -1, "delta": 0.5}, "E_INPUT", "two errors: row A with a delta and a negative maturity [structural] [domain]")
    err("rfet_ke", rf, {"as_of": "2026-06-31", "observations": []}, "E_SCHEMA", "as_of not a date")
    err("rfet_ke", rf, {"observations": ["2026-01-01"]}, "E_SCHEMA", "as_of missing")
    err("rfet_ke", rf, {"as_of": "2026-06-30", "observations": ["2026-1-1"]}, "E_SCHEMA", "an observation not an ISO date")
    err("lh_ke", lh, {"category": "IR_exotic"}, "E_SCHEMA", "category not listed")
    err("lh_ke", lh, {"category": "FX_pairs", "fx_pair": "EUR/USD"}, "E_INPUT", "category and fx_pair both given (KR-306)")
    err("lh_ke", lh, {"maturity_days": 5}, "E_INPUT", "no category, fx_pair or constituents (KR-306)")
    err("lh_ke", lh, {"fx_pair": "EURUSD"}, "E_SCHEMA", "fx_pair not of the form AAA/BBB")
    err("lh_ke", lh, {"fx_pair": "EUR/EUR"}, "E_DOMAIN", "fx_pair with one currency twice (KR-306)")
    err("lh_ke", lh, {"constituents": [{"weight": 0.8, "n": 10}, {"weight": 0.1, "n": 20}]}, "E_DOMAIN", "weights sum to 0.9 (KR-60)")
    err("lh_ke", lh, {"constituents": [{"weight": 1, "n": 30}]}, "E_DOMAIN", "constituent n 30 is not a horizon (KR-306)")
    err("lh_ke", lh, {"constituents": [{"weight": -0.2, "n": 10}, {"weight": 1.2, "n": 20}]}, "E_DOMAIN", "negative weight (KR-306)")
    err("lh_ke", lh, {"constituents": []}, "E_INPUT", "no constituents (KR-306)")
    err("lh_ke", lh, {"category": "EQ_large_cap", "maturity_days": -1}, "E_DOMAIN", "negative maturity_days")
    err("lh_ke", lh, {"category": "EQ_large_cap", "maturity_days": "NaN"}, "E_DOMAIN", "E1: maturity_days NaN")
    err("lh_ke", lh, {"category": "EQ_large_cap", "fx_pair": "EUR/USD", "maturity_days": -1}, "E_INPUT",
        "two errors: category and fx_pair both given and negative maturity_days [structural] [domain]")
    s.write()
    return s


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_k"
    try:
        a = gen_drc()
        b = gen_ima()
    finally:
        common.GOLDEN = keep
    for s in (a, b):
        ids = [c["case_id"] for c in s.cases]
        assert len(ids) == len(set(ids)), s.name
    va = sum(c["expected"]["status"] == "ok" for c in a.cases)
    vb = sum(c["expected"]["status"] == "ok" for c in b.cases)
    assert (va, vb) == (18, 33), (va, vb)  # value cases of the two spec tables


if __name__ == "__main__":
    main()
