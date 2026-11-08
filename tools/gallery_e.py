"""Stage E gallery pages: volatility surfaces, local volatility, the swaption cube and vol term structures.

Used by tools/build_gallery.py. Standard library only and no financial logic: it reads CLI outputs,
checks their shape against the output contract below, and draws them. Each page is Planned until its
`cli` names an operation that all four CLIs answer and the example file exists; then build_gallery.py
runs the four CLIs and this module renders the result.

Language sessions: when an operation lands, set `cli` (and fix `examples` if the name differs from the
placeholder), add the example file under examples/ with case_id `example-synthetic-...`, make the
outputs follow `contract`, then run `python tools/build_gallery.py`. Placeholder operation names are
marked PLACEHOLDER and must be replaced by the names in the stage E spec.

Charts are sized for a phone: the view box is 360 units wide, so at 375 px the text renders near
12 px. Colours come from the site's CSS variables (--c1, --c2, --line, --bg, currentColor), which the
site redefines for dark mode, so no colour is fixed in the SVG.
"""
import html
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "datasets" / "golden" / "stage_e"
SYNTHETIC = "Synthetic inputs, not market data."

# Output contracts. Keys are the CLI output fields the renderer reads; the CLI may return more.
CONTRACTS = {
    "surface": "`expiries` (years, ascending), `strikes` (ascending), `vols` as a list per expiry of one value per strike",
    "term": "`expiries` (years, ascending) and `atm_vols`; optional `forward_vols`, one per expiry",
    "cube": "`expiries`, `tenors` (years), `strikes` (offsets from ATM in bp, with 0 present), `vols` as [expiry][tenor][strike]",
}

STAGE_E = {
    "vol-surface": {
        "kind": "surface", "title": "Implied volatility surface, calibrated", "short": "Implied vol surface",
        "cli": None, "examples": {"vol.surface.grid": "vol_surface_grid_e.json"},  # PLACEHOLDER operation and file
        "value": "Implied volatility",
        "shows": "A full implied volatility surface calibrated to option quotes, as a heat grid by expiry and strike, with smile slices at three expiries. The surface is checked for calendar and butterfly arbitrage on its grid.",
        "inputs": "Synthetic option quotes on a strike and expiry grid, a spot, and flat funding and dividend curves, copied from a golden case.",
        "oracle": "Calibrated surfaces are compared with QuantLib where it has the same parametrisation, and with hand cases for the arbitrage checks. Targets are set in the stage E spec.",
    },
    "local-vol": {
        "kind": "surface", "title": "Local volatility (Dupire)", "short": "Local volatility",
        "cli": None, "examples": {"vol.local.grid": "vol_local_grid_e.json"},  # PLACEHOLDER operation and file
        "value": "Local volatility",
        "shows": "Dupire local volatility derived from an arbitrage-free implied surface, as a heat grid by time and spot level, with slices at three times. Local volatility is the diffusion coefficient that reprices every vanilla on the surface.",
        "inputs": "A synthetic implied surface, the same parameters as a golden case, evaluated on a time and strike grid.",
        "oracle": "Compared with QuantLib `LocalVolSurface` on the same implied surface, and with the flat-surface hand case, where local and implied volatility are equal.",
    },
    "swaption-cube": {
        "kind": "cube", "title": "Swaption volatility cube", "short": "Swaption cube",
        "cli": None, "examples": {"rates.swaption.cube": "swaption_cube_e.json"},  # PLACEHOLDER operation and file
        "value": "Normal volatility",
        "shows": "Swaption volatilities by option expiry, underlying swap tenor and strike: the at-the-money matrix as a heat grid, and smiles for the shortest and longest tenor at a middle expiry.",
        "inputs": "A synthetic at-the-money matrix and SABR smile parameters per expiry and tenor, copied from a golden case.",
        "oracle": "Compared with QuantLib `SabrSwaptionVolatilityCube` where the conventions match, and with hand cases at the at-the-money strike.",
    },
    "vol-term-structure": {
        "kind": "term", "title": "Volatility term structures", "short": "Vol term structure",
        "cli": None, "examples": {"vol.surface.term": "vol_term_structure_e.json"},  # PLACEHOLDER operation and file
        "value": "Volatility",
        "shows": "At-the-money implied volatility by expiry, and the forward volatility between consecutive expiries that it implies. A negative forward variance would mean calendar arbitrage.",
        "inputs": "A synthetic surface's at-the-money total variance by expiry, copied from a golden case.",
        "oracle": "Forward variance is checked against hand cases. The at-the-money volatilities come from the same surface as the implied surface page.",
    },
}


def is_live(spec):
    return bool(spec.get("cli")) and all((ROOT / "examples" / f).is_file() for f in spec["examples"].values())


def golden(ops):
    import json
    counts, total = {}, 0
    for path in sorted(GOLDEN.glob("*.json")) if GOLDEN.is_dir() else []:
        for c in json.loads(path.read_text(encoding="utf-8"))["cases"]:
            if c["operation"] not in ops or c["expected"].get("status") != "ok":
                continue
            key = f"{c['operation']}: {', '.join(c['verified_by'])}"
            counts[key] = counts.get(key, 0) + 1
            total += 1
    return {"operations": list(ops), "cases": total, "by_source": counts}


# ---- shape checks -------------------------------------------------------------------------------

def _nums(v, name):
    if not isinstance(v, list) or not v or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in v):
        raise ValueError(f"{name}: expected a non-empty list of finite numbers")
    return [float(x) for x in v]


def check_contract(kind, out):
    """Returns the fields a renderer needs, or raises ValueError naming the first broken field."""
    if kind == "term":
        e = _nums(out.get("expiries"), "expiries")
        atm = _nums(out.get("atm_vols"), "atm_vols")
        if len(atm) != len(e):
            raise ValueError("atm_vols: one per expiry")
        fwd = out.get("forward_vols")
        if fwd is not None and len(_nums(fwd, "forward_vols")) != len(e):
            raise ValueError("forward_vols: one per expiry")
        return {"expiries": e, "atm_vols": atm, "forward_vols": fwd}
    e, k = _nums(out.get("expiries"), "expiries"), _nums(out.get("strikes"), "strikes")
    v = out.get("vols")
    if kind == "surface":
        if not isinstance(v, list) or len(v) != len(e):
            raise ValueError("vols: one row per expiry")
        rows = [_nums(r, f"vols[{i}]") for i, r in enumerate(v)]
        if any(len(r) != len(k) for r in rows):
            raise ValueError("vols: one value per strike in every row")
        return {"expiries": e, "strikes": k, "vols": rows}
    t = _nums(out.get("tenors"), "tenors")
    if not isinstance(v, list) or len(v) != len(e) or any(not isinstance(p, list) or len(p) != len(t) for p in v):
        raise ValueError("vols: [expiry][tenor][strike]")
    cube = [[_nums(r, f"vols[{i}][{j}]") for j, r in enumerate(p)] for i, p in enumerate(v)]
    if any(len(r) != len(k) for p in cube for r in p):
        raise ValueError("vols: one value per strike")
    if 0.0 not in k:
        raise ValueError("strikes: the ATM offset 0 must be present")
    return {"expiries": e, "tenors": t, "strikes": k, "vols": cube}


# ---- phone-sized charts -------------------------------------------------------------------------

W, H, ML, MR, MT, MB = 360, 260, 46, 10, 30, 40
FONT = 'style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"'
STROKES = [("var(--c1)", ""), ("var(--c2)", ""), ("var(--c1)", "stroke-dasharray:5 3;"), ("var(--c2)", "stroke-dasharray:5 3;")]


def fmt(v):
    return f"{v:.4g}"


def _ticks(lo, hi, n=4):
    if lo == hi:
        lo, hi = lo - abs(lo) * 0.1 - 1e-9, hi + abs(hi) * 0.1 + 1e-9
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)
    return [round(i * step, 12) for i in range(math.floor(lo / step), math.ceil(hi / step) + 1)]


def _thin(n, most=6):
    """Indices to label so that at most `most` labels show on a narrow screen."""
    step = max(1, math.ceil(n / most))
    return set(range(0, n, step)) | {n - 1}


def _wrap(svg, caption):
    return '<div class="chart">' + svg + f"<p>{html.escape(caption)}</p></div>"


def heatmap(title, xs, ylabels, z, xlabel, caption, unit="value"):
    """One cell per (row, column), shaded from the lowest to the highest value read from CLI output.
    z[i][j] is row i (ylabels), column j (xs). A five-step key under the grid names the value range."""
    if not xs or not ylabels or len(z) != len(ylabels) or any(len(r) != len(xs) for r in z):
        raise ValueError("heatmap grid must be non-empty and match rows x columns")
    flat = [v for r in z for v in r]
    lo, hi = min(flat), max(flat)
    key_h = 34
    total_h = H + key_h
    cw, ch = (W - ML - MR) / len(xs), (H - MB - MT) / len(ylabels)
    out = [f'<svg viewBox="0 0 {W} {total_h}" role="img" aria-label="{html.escape(title)}, synthetic data" xmlns="http://www.w3.org/2000/svg" {FONT}>',
           f'<text x="0" y="16" style="font-weight:600;font-size:13px">{html.escape(title)}</text>']
    rows_shown = _thin(len(ylabels), 8)
    for i, row in enumerate(z):
        y = MT + i * ch
        if i in rows_shown:
            out.append(f'<text x="{ML - 4}" y="{y + ch / 2 + 4:.1f}" text-anchor="end">{html.escape(str(ylabels[i]))}</text>')
        for j, v in enumerate(row):
            a = 0.12 + 0.88 * ((v - lo) / (hi - lo) if hi > lo else 0.5)
            out.append(f'<rect x="{ML + j * cw:.1f}" y="{y:.1f}" width="{cw:.1f}" height="{ch:.1f}" style="fill:var(--c1);fill-opacity:{a:.2f};stroke:var(--bg);stroke-width:.5">'
                       f'<title>{html.escape(str(ylabels[i]))}, {html.escape(xlabel)} {fmt(xs[j])}: {v:.6g}</title></rect>')
    for j in sorted(_thin(len(xs))):
        out.append(f'<text x="{ML + (j + .5) * cw:.1f}" y="{H - MB + 15}" text-anchor="middle">{fmt(xs[j])}</text>')
    out.append(f'<text x="{(ML + W - MR) / 2}" y="{H - 8}" text-anchor="middle">{html.escape(xlabel)}</text>')
    ky, sw = H + 4, (W - ML - MR) / 5
    for s in range(5):
        out.append(f'<rect x="{ML + s * sw:.1f}" y="{ky}" width="{sw:.1f}" height="10" style="fill:var(--c1);fill-opacity:{0.12 + 0.22 * s:.2f};stroke:var(--line);stroke-width:.5"/>')
    out.append(f'<text x="{ML}" y="{ky + 24}">{html.escape(unit)} {fmt(lo)}</text>')
    out.append(f'<text x="{W - MR}" y="{ky + 24}" text-anchor="end">{fmt(hi)}</text>')
    out.append(f'<text x="{(ML + W - MR) / 2}" y="{ky + 24}" text-anchor="middle" style="font-style:italic">synthetic</text>')
    return _wrap("".join(out) + "</svg>", caption)


def lines(title, xlabel, ylabel, series, caption):
    """series: [(name, [(x, y), ...])], at most four. The legend sits under the plot, one row per series,
    so long names never run off a narrow screen."""
    if not series or len(series) > 4 or any(len(p) < 2 for _, p in series):
        raise ValueError("lines: one to four series of two or more points")
    xs = [x for _, p in series for x, _ in p]
    ys = [y for _, p in series for _, y in p]
    xt, yt = _ticks(min(xs), max(xs)), _ticks(min(ys), max(ys))
    leg_h = 18 * len(series) if len(series) > 1 else 0
    total_h = H + leg_h

    def sx(v):
        return ML + (v - xt[0]) / (xt[-1] - xt[0]) * (W - ML - MR)

    def sy(v):
        return H - MB - (v - yt[0]) / (yt[-1] - yt[0]) * (H - MB - MT)

    out = [f'<svg viewBox="0 0 {W} {total_h}" role="img" aria-label="{html.escape(title)}, synthetic data" xmlns="http://www.w3.org/2000/svg" {FONT}>',
           f'<text x="0" y="16" style="font-weight:600;font-size:13px">{html.escape(title)}</text>']
    for v in yt:
        out.append(f'<line x1="{ML}" x2="{W - MR}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" style="stroke:var(--line)"/>')
        out.append(f'<text x="{ML - 4}" y="{sy(v) + 4:.1f}" text-anchor="end">{fmt(v)}</text>')
    for v in xt:
        out.append(f'<text x="{sx(v):.1f}" y="{H - MB + 15}" text-anchor="middle">{fmt(v)}</text>')
    out.append(f'<text x="{(ML + W - MR) / 2}" y="{H - 8}" text-anchor="middle">{html.escape(xlabel)}</text>')
    out.append(f'<text transform="translate(11 {(MT + H - MB) / 2}) rotate(-90)" text-anchor="middle">{html.escape(ylabel)}</text>')
    for n, (name, pts) in enumerate(series):
        colour, dash = STROKES[n]
        path = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in pts)
        out.append(f'<polyline points="{path}" style="fill:none;stroke:{colour};stroke-width:2;{dash}stroke-linejoin:round"><title>{html.escape(name)}</title></polyline>')
        if len(series) > 1:
            ly = H + 6 + 18 * n
            out.append(f'<line x1="{ML}" x2="{ML + 22}" y1="{ly}" y2="{ly}" style="stroke:{colour};stroke-width:2;{dash}"/>')
            out.append(f'<text x="{ML + 28}" y="{ly + 4}">{html.escape(name)}</text>')
    return _wrap("".join(out) + "</svg>", caption)


# ---- charts and numbers per kind ----------------------------------------------------------------

def _pick(n, k=3):
    return sorted({0, n // 2, n - 1})[:k] if n > 1 else [0]


def charts(kind, spec, g, caption):
    if kind == "surface":
        e, k, v = g["expiries"], g["strikes"], g["vols"]
        out = [heatmap(f"{spec['value']} surface", k, [f"{t:g}y" for t in e], v, "Strike", caption, unit=spec["value"].split()[0])]
        out.append(lines(f"{spec['value']} slices", "Strike", spec["value"], [(f"{e[i]:g}y", list(zip(k, v[i]))) for i in _pick(len(e))], caption))
        return out
    if kind == "term":
        s = [("ATM implied", list(zip(g["expiries"], g["atm_vols"])))]
        if g["forward_vols"] is not None:
            s.append(("Forward", list(zip(g["expiries"], [float(x) for x in g["forward_vols"]]))))
        return [lines("Volatility term structure", "Expiry, years", spec["value"], s, caption)]
    e, t, k, v = g["expiries"], g["tenors"], g["strikes"], g["vols"]
    atm = k.index(0.0)
    out = [heatmap("ATM normal volatility, expiry by tenor", t, [f"{x:g}y" for x in e], [[v[i][j][atm] for j in range(len(t))] for i in range(len(e))],
                   "Swap tenor, years", caption, unit="Vol")]
    mid = len(e) // 2
    out.append(lines(f"Smiles at {e[mid]:g}y expiry", "Strike offset, bp", spec["value"],
                     [(f"{t[j]:g}y tenor", list(zip(k, v[mid][j]))) for j in sorted({0, len(t) - 1})], caption))
    return out


def numbers(kind, g, table):
    f = lambda x: f"{x:.6g}"
    if kind == "surface":
        return table(["Expiry \\ strike"] + [f(x) for x in g["strikes"]], [[f"{t:g}y"] + [f(x) for x in r] for t, r in zip(g["expiries"], g["vols"])])
    if kind == "term":
        fw = g["forward_vols"] or [None] * len(g["expiries"])
        return table(["Expiry", "ATM vol", "Forward vol"], [[f"{t:g}", f(a), "" if w is None else f(w)] for t, a, w in zip(g["expiries"], g["atm_vols"], fw)])
    atm = g["strikes"].index(0.0)
    return "At the money:\n\n" + table(["Expiry \\ tenor"] + [f"{t:g}y" for t in g["tenors"]],
                                       [[f"{e:g}y"] + [f(p[atm]) for p in g["vols"][i]] for i, e in enumerate(g["expiries"])])


# ---- pages --------------------------------------------------------------------------------------

def planned_page(slug, spec, evidence):
    op, ex = next(iter(spec["examples"].items()))
    return f"""# {spec['title']}

<p class="note">Status: Planned, stage E (in progress, target v0.5). No CLI operation exists yet, so this page has no numbers or charts. Nothing here is a result.</p>

## What it is

{spec['shows']}

## Inputs

{spec['inputs']} {SYNTHETIC}

## Command

Not yet. When the operation lands, the page shows the command for `examples/{ex}`.

## Charts

None yet. Charts are drawn only from real CLI output when the gallery is built.

## Numbers

None yet.

## Four-language agreement

None yet. The page fills in when all four CLIs answer the operation.

## Oracle evidence and limits

{spec['oracle']} Golden cases with an `ok` result in `datasets/golden/stage_e/` so far: {evidence['cases']}.

## Output contract

The renderer reads {CONTRACTS[spec['kind']]} from the operation's outputs. Operation name `{op}` is a placeholder until the stage E spec fixes it. See [the gallery index](README.md).
"""


def live_page(slug, spec, d, bg):
    op, ex = next(iter(spec["examples"].items()))
    g = check_contract(spec["kind"], d["reference"][op])
    cap = f"{SYNTHETIC} From the Python CLI; exact values are in the tables and data file."
    e = d["evidence"]
    agree = [[r["output"], r["count"]] + [repr(r["last"][k]) if not isinstance(r["last"][k], (list, dict)) else "list" for k in bg.LANGS]
             + ["differ" if r["largest_difference"] is None else f"{r['largest_difference']:.3g}"] for r in d["agreement"]]
    ev_rows = [[k, n] for k, n in sorted(e["by_source"].items())]
    return f"""# {spec['title']}

{bg.status_block(d)}

## What it is

{spec['shows']} Stage E, target v0.5.

## Inputs

{spec['inputs']} {SYNTHETIC} Input: [`examples/{ex}`](../../examples/{ex}).

## Command

Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:

```bash
rust/target/release/quantforge run < examples/{ex}
```

Raw numbers: [`docs/curves/data/{slug}.json`](data/{slug}.json).

## Charts

{chr(10).join(charts(spec['kind'], spec, g, cap))}

## Numbers

{numbers(spec['kind'], g, bg.table)}

## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

{bg.table(['Output', 'Values', 'Last value: Java', 'C++', 'Python', 'Rust', 'Largest difference, any value'], agree)}

## Oracle evidence and limits

{spec['oracle']}

{e['cases']} golden cases with status ok in `datasets/golden/stage_e` for {', '.join('`' + o + '`' for o in e['operations'])}, by `verified_by`:

{bg.table(['Operation: sources', 'Cases'], ev_rows)}

Limits: one synthetic input, so the page shows the method, not a market. Arbitrage flags are checks at grid points only.

{SYNTHETIC}
"""


def page(slug, spec, d, bg):
    return live_page(slug, spec, d, bg) if is_live(spec) and d is not None and "reference" in d else planned_page(slug, spec, golden(spec["examples"]))
