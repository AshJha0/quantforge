# Tutorial 52: one quote moves, so rebuild only what it touches

<!-- tutorial:only python -->

The plain idea: in a sequential bootstrap each discount factor depends only on the quotes up to its own maturity. When one quote ticks, the pillars before it cannot change, so only that pillar and the later ones need solving again. The shortcut is only acceptable if it gives the same curve as rebuilding everything, bit for bit, and if it refuses to patch a cache that is already stale.

You will bootstrap a three-pillar curve, move the second and then the third quote, check each patched curve against a full rebuild, and watch a stale cache get refused. Budget 10 minutes.

<p class="note">Stage K. The operations <code>curve.bootstrap.par_annual</code> and <code>curve.incremental.update</code> are on the integration branch <code>k-r1</code> in all four builds (merged 2026-11-19; not yet released) (spec <code>specifications/02-curves/incremental-update.md</code> 1.0.0, ruling KR-5). Acceptance evidence files: Python and Java; C++ and Rust run the same properties in their unit tests without writing evidence files (<code>program/STAGE_K_W1_HANDOVER.md</code>). The incremental path on the stage B production bootstrap is in all four builds: 10,000 of 10,000 moves bit-identical to a full rebuild in each. Step 1 restates the rule with the standard library on the golden inputs; Step 2 calls the library, and CI checks that it prints the lines shown under Step 1.</p>

Terms, defined here. A **par swap** with annual payments and accrual 1 has fixed rate `S_k` that makes it worth zero. **Pillar** `k` is the discount factor `P_k` at year `k`. **Bit for bit** means the two binary64 numbers are the same 64 bits, not merely close.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. Step 1 uses the Python standard library only.

## Step 1: bootstrap, patch, compare

```python
import math

# Annual par bootstrap and the incremental update of curve.incremental.update, goldens inc_k-0001 to 0004,
# restated with the standard library.


def bootstrap(quotes):
    p, total = [], 0.0
    for s in quotes:
        p.append((1 - s * total) / (1 + s))  # P_k = (1 - S_k sum_{i<k} P_i) / (1 + S_k)
        total += p[-1]
    return p


def update(prev_quotes, prev_p, new_quotes):
    assert bootstrap(prev_quotes) == prev_p, "stale cache: E_INPUT"  # bit for bit, or refuse
    j = next((i for i, (a, b) in enumerate(zip(prev_quotes, new_quotes)) if a != b), None)
    if j is None:
        return list(prev_p), None, 0
    p, total = list(prev_p[:j]), sum(prev_p[:j])  # pillars before j are copied, never recomputed
    for s in new_quotes[j:]:
        p.append((1 - s * total) / (1 + s))
        total += p[-1]
    return p, j, len(new_quotes) - j


base = [0.02, 0.025, 0.03]
p0 = bootstrap(base)
golden = [0.980392156862745098, 0.951697752271640363, 0.914599323034920812]
assert all(abs(a - b) <= 1e-15 for a, b in zip(p0, golden))
print("inc_k-0001", [f"{x:.15f}" for x in p0])
for case, new in (("inc_k-0002", [0.02, 0.026, 0.03]), ("inc_k-0003", [0.02, 0.025, 0.031]), ("inc_k-0004", base)):
    p, j, n = update(base, p0, new)
    assert p == bootstrap(new)  # the shortcut equals a full rebuild, bit for bit
    same = sum(a == b for a, b in zip(p, p0))
    print(f"{case} first_changed_index {j} recomputed {n} pillars equal to the base {same} last {p[-1]:.15f}")
stale = p0[:2] + [math.nextafter(p0[2], math.inf)]  # one unit in the last place too high
try:
    update(base, stale, [0.02, 0.026, 0.03])
except AssertionError as e:
    print("inc_k-0006 refused:", e)
```

Output (CI checks that Step 2 prints these lines):

<!-- tutorial:expect -->
```text
inc_k-0001 ['0.980392156862745', '0.951697752271640', '0.914599323034921']
inc_k-0002 first_changed_index 1 recomputed 2 pillars equal to the base 1 last 0.914654171439768
inc_k-0003 first_changed_index 2 recomputed 1 pillars equal to the base 2 last 0.911838227756386
inc_k-0004 first_changed_index None recomputed 0 pillars equal to the base 3 last 0.914599323034921
inc_k-0006 refused: stale cache: E_INPUT
```

### Reading the numbers

- **The base curve.** `P_1 = 1/1.02 = 0.98039...`; `P_2 = (1 - 0.025 P_1)/1.025 = 0.95170...`; `P_3 = (1 - 0.03 (P_1 + P_2))/1.03 = 0.91460...` (`inc_k-0001`; the spec's derivation, checked to 30 digits by mpmath in the oracle).
- **A 2-year move.** Raising the 2-year quote from 2.5% to 2.6% leaves `P_1` copied, and recomputes two pillars. The last pillar moves from 0.914599 to 0.914654: the 3-year swap's fixed leg leans on `P_2`, which fell, so `P_3` rises slightly (`inc_k-0002`).
- **A 3-year move.** Only `P_3` is recomputed: 0.911838 (`inc_k-0003`). No change at all copies everything and recomputes nothing (`inc_k-0004`).
- **The stale cache.** Moving the last cached pillar up by one unit in the last place makes the cache disagree with its own quotes, and the update refuses rather than patch it (`inc_k-0006`, `E_INPUT` in the library).
- **Binary64 against the decimals.** The goldens print the exact decimal values; the binary64 bootstrap gives `0.9516977522716404` where the decimal is `0.951697752271640363`, inside the 1e-15 tolerance. The cache check compares binary64 with binary64, so it is exact.

### The formal statement, checked against the spec

From `specifications/02-curves/incremental-update.md` (ruling KR-5; read 2026-11-19).

- `P_k = (1 - S_k sum_{i<k} P_i) / (1 + S_k)`. If quotes change only at indices `>= j` (0-based), `P_0..P_{j-1}` are unchanged and `P_j..P_{n-1}` follow from the same recursion. Hagan and West (2006), section 2, is cited for the bootstrap identity (UNVERIFIED section number in the spec).
- `curve.incremental.update` checks that `previous_discount_factors` equals the bootstrap of `previous_quotes` bit for bit; if not, `E_INPUT`. Lengths that differ are `E_INPUT` (`inc_k-0005`).
- Acceptance (fixed before the run): the goldens in four languages; for 10,000 random quote vectors and random single or multi-index changes, the update equals a full rebuild to 1e-12 relative with copied pillars bit-identical; and the same premise on the stage B production bootstrap.
- Evidence (measured by the k-w1 lane, 2026-11-19): all 10,000 vectors bit-identical to a full rebuild (largest relative difference 0), key `incremental_property`; on the 10 stage B log-linear bootstrap goldens, 45 single-quote moves of 1 bp, in every one the first pillar that changes is the moved quote's and every earlier pillar is bit-identical, key `incremental_property_stage_b`. Python and Java (`program/stage_k_w1/`); C++ and Rust run the same properties in their unit tests. On the stage B production bootstrap itself (the follow-up lane, 2026-11-19), all four builds patch 10,000 of 10,000 moves bit-identically to a full rebuild, key `incremental_property_stage_b_patched` (`specifications/02-curves/incremental-update.md`, "Acceptance evidence").

## Step 2: the same cases through the library

This block calls the library on the goldens in `datasets/golden/stage_k/`. It was turned on at integration (2026-11-19) and printed the same lines as Step 1; CI now checks them.

<!-- tutorial:run python -->
```python
# Goldens inc_k-0001 to 0004 and 0006 through curve.bootstrap.par_annual and curve.incremental.update.
import json

from quantforge_core.cli.main import run_case

cases = {c["case_id"]: c for c in json.load(open("datasets/golden/stage_k/inc_k.json", encoding="utf-8"))["cases"]}


def run(case_id):
    c = cases[case_id]
    return c, run_case(json.dumps({"schema_version": "1.0", "case_id": case_id, "operation": c["operation"], "inputs": c["inputs"]}))


c, r = run("inc_k-0001")
p0 = r["outputs"]["discount_factors"]
assert all(abs(a - b) <= 1e-15 for a, b in zip(p0, c["expected"]["outputs"]["discount_factors"]))
print("inc_k-0001", [f"{x:.15f}" for x in p0])
for case in ("inc_k-0002", "inc_k-0003", "inc_k-0004"):
    c, r = run(case)
    out = r["outputs"]
    p = out["discount_factors"]
    same = sum(a == b for a, b in zip(p, p0))
    print(f"{case} first_changed_index {out['first_changed_index']} recomputed {out['recomputed']} pillars equal to the base {same} last {p[-1]:.15f}")
c, r = run("inc_k-0006")
print("inc_k-0006 refused: stale cache:", r["error"]["code"])
```

## For practitioners

- **Where the time goes.** In a real bootstrap the expensive part is each pillar's root solve; skipping the pillars before the first moved quote saves work in proportion to how far out the move is. A front-end tick saves nothing.
- **The production bootstrap has no incremental entry point.** On the stage B bootstrap only the premise is checked: earlier pillars cannot move. The patched-against-rebuild check is on the hand-sized instrument set here (handover limitation).
- **Refuse, do not patch, a stale cache.** A cache built from other quotes would make the patched curve silently wrong. The bit-for-bit check is cheap: one full bootstrap.

## Common mistakes

- **Assuming a global interpolation keeps the property.** With a spline through all pillars, every forward between pillars depends on every quote. The premise holds for the sequential bootstrap, not for every curve.
- **Comparing with a tolerance.** "Close to a full rebuild" hides a cache bug that "bit for bit" catches.

## What you just did

You built a three-pillar par curve, patched it for two different quote moves, proved each patch equals a full rebuild bit for bit, and saw a cache one unit in the last place off refused.

## Try next

- Move the first quote to 2.1% and predict `first_changed_index` and `recomputed` before you run it.

## References and further reading

- This project: `specifications/02-curves/incremental-update.md`, `specifications/stage-k-rulings-w1.md`; the stage B bootstrap, [`curve-framework.md`](../../specifications/02-curves/curve-framework.md).
- P. S. Hagan and G. West, "Interpolation methods for curve construction", *Applied Mathematical Finance* 13(2), 2006 (cited in the spec; free preprint; section number UNVERIFIED).
