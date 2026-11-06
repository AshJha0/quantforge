"""RNG, Sobol, Monte Carlo golden cases."""
import math
import statistics

import mpmath as mp
import QuantLib as ql
from scipy.stats import qmc

from qf_oracle.common import Suite, f, note
from qf_oracle.rng import Sobol, Xo, bs, ppnd16, splitmix, true_inverse_normal

G = "oracle/python/gen_random.py"
# Published vectors, from the tests of rand_xoshiro 0.7.0, which state they came from the authors' reference C code.
XO_REF = [11520, 0, 1509978240, 1215971899390074240, 1216172134540287360, 607988272756665600,
          16172922978634559625, 8476171486693032832, 10595114339597558777, 2904607092377533576]
SM_REF = [1985237415132408290, 2979275885539914483, 13511426838097143398, 8488337342461049707, 15141737807933549159]


def rng():
    s = Suite("rng", "specifications/01-core/rng.md", G)
    x = Xo(state=[1, 2, 3, 4])
    got = [x.next() for _ in range(10)]
    assert got == XO_REF, got
    g = splitmix(1477776061723855037)
    assert [next(g) for _ in range(5)] == SM_REF
    note("rng: xoshiro256** and SplitMix64 match the published reference vectors")
    s.add("core.rng.set_state_next_u64", {"state": ["1", "2", "3", "4"], "count": 10}, {"values": [str(v) for v in XO_REF]},
          cls="bit_exact", verified=["published-reference-vector"])
    for seed, stream, skip in ((0, 0, 0), (1, 0, 0), (20261106, 0, 0), (18446744073709551615, 0, 5), (42, 1, 0), (42, 3, 2), (42, 1023, 0)):
        inp = {"seed": str(seed), "stream": stream, "count": 8}
        if skip:
            inp["skip"] = skip
        ver = ["pure-integer-replay"]
        a = Xo(seed=seed, stream=stream)
        for _ in range(skip):
            a.next()
        s.add("core.rng.next_u64", inp, {"values": [str(a.next()) for _ in range(8)]}, cls="bit_exact", verified=ver)
        a = Xo(seed=seed, stream=stream)
        for _ in range(skip):
            a.next()
        us = [a.uniform() for _ in range(8)]
        s.add("core.rng.uniforms", inp, {"values": us}, cls="bit_exact", verified=ver)
        s.add("core.rng.normals", inp, {"values": [ppnd16(u) for u in us]}, cls="common_rng", verified=ver)
    ps = [2.0 ** -53, 1e-300, 1e-20, 1e-10, 1e-5, 0.001, 0.01, 0.07, 0.075, 0.0751, 0.25, 0.5, 0.75, 0.925, 0.99, 0.999999, 1 - 2.0 ** -53]
    worst = 0.0
    zs = []
    for p in ps:
        t = true_inverse_normal(p)
        z = ppnd16(p)
        zs.append(f(t))
        if t != 0:
            worst = max(worst, abs(float((z - t) / t)))
    note(f"rng: PPND16 worst relative error against 50-digit erfinv over {len(ps)} points: {worst:.2e}")
    assert worst < 1e-15
    s.add("core.rng.inverse_normal", {"p": ps}, {"z": zs}, cls="common_rng", verified=["mpmath-50"])
    s.add("core.rng.inverse_normal", {"p": [0.0]}, error="E_DOMAIN", tags=["invalid"])
    s.add("core.rng.inverse_normal", {"p": [1.0]}, error="E_DOMAIN", tags=["invalid"])
    s.add("core.rng.next_u64", {"seed": "-1", "stream": 0, "count": 1}, error="E_SCHEMA", tags=["invalid"])
    s.add("core.rng.next_u64", {"seed": "1", "stream": 1024, "count": 1}, error="E_SCHEMA", tags=["invalid"])
    s.add("core.rng.set_state_next_u64", {"state": ["0", "0", "0", "0"], "count": 1}, error="E_INPUT", tags=["invalid"])
    s.write()


def sobol():
    s = Suite("sobol", "specifications/01-core/sobol.md", G)
    for dims, count, skip in ((1, 16, 0), (2, 16, 0), (3, 40, 0), (8, 33, 0), (21, 20, 0), (64, 10, 0), (5, 10, 1000), (64, 3, 4095)):
        q = ql.SobolRsg(dims, 0, ql.SobolRsg.JoeKuoD6)
        o = Sobol(dims)
        for _ in range(skip):
            o.next()
            q.nextSequence()
        pts = [o.next() for _ in range(count)]
        qp = [list(q.nextSequence().value()) for _ in range(count)]
        assert pts == qp, (dims, skip)
        sp = qmc.Sobol(dims, scramble=False, bits=32).random(skip + count + 1)[skip + 1:]
        assert all(list(map(float, a)) == b for a, b in zip(sp, pts)), "scipy"
        inp = {"dimensions": dims, "count": count} | ({"skip": skip} if skip else {})
        s.add("core.sobol.points", inp, {"points": pts}, cls="bit_exact", verified=["own-bit-code", "quantlib-1.44", "scipy-1.18.1"])
    note("sobol: own code, QuantLib JoeKuoD6 and SciPy agree bit for bit on all stored cases")
    s.add("core.sobol.points", {"dimensions": 65, "count": 1}, error="E_INPUT", tags=["invalid"])
    s.add("core.sobol.points", {"dimensions": 0, "count": 1}, error="E_INPUT", tags=["invalid"])
    s.write()


def mc_replay(inp):
    S, K, r, q, sig, t = (inp[k] for k in ("spot", "strike", "r", "q", "sigma", "t"))
    N, m, method = inp["paths"], inp.get("steps", 1), inp["method"]
    dt = t / m
    drift = (r - q - sig * sig / 2) * dt
    vol = sig * math.sqrt(dt)
    disc = math.exp(-r * t)
    sign = 1.0 if inp["option"] == "CALL" else -1.0
    x0 = math.log(S)

    def pay(zs, neg=False):
        x = x0
        for z in zs:
            x += drift + vol * (-z if neg else z)
        st = math.exp(x)
        return disc * max(sign * (st - K), 0.0), disc * st

    rng = Xo(seed=int(inp["seed"]), stream=inp.get("stream", 0))
    sob = Sobol(m) if method == "SOBOL" else None
    ys, cs = [], []
    for _ in range(N):
        zs = [ppnd16(u) for u in sob.next()] if sob else [ppnd16(rng.uniform()) for _ in range(m)]
        p, c = pay(zs)
        if method == "ANTITHETIC":
            p = 0.5 * (p + pay(zs, True)[0])
        ys.append(p)
        cs.append(c)
    if method == "CONTROL_VARIATE":
        mc = S * math.exp(-q * t)
        my, mcbar = math.fsum(ys) / N, math.fsum(cs) / N
        cov = math.fsum((a - my) * (b - mcbar) for a, b in zip(ys, cs)) / (N - 1)
        var = math.fsum((b - mcbar) ** 2 for b in cs) / (N - 1)
        beta = cov / var
        ys = [a - beta * (b - mc) for a, b in zip(ys, cs)]
    mean = math.fsum(ys) / N
    sd = statistics.stdev(ys, mean)
    return mean, sd / math.sqrt(N)


def monte_carlo():
    s = Suite("monte_carlo", "specifications/01-core/monte-carlo.md", G)
    op = "core.mc.gbm_european"
    base = {"spot": 100.0, "strike": 100.0, "r": 0.05, "q": 0.02, "sigma": 0.2, "t": 1.0, "seed": "20261106"}
    runs = [("CALL", "PLAIN", 100000, 1, {}), ("PUT", "PLAIN", 50000, 1, {}), ("CALL", "PLAIN", 20000, 4, {}), ("CALL", "PLAIN", 50000, 1, {"stream": 7}),
            ("CALL", "ANTITHETIC", 50000, 1, {}), ("CALL", "CONTROL_VARIATE", 50000, 1, {}), ("PUT", "CONTROL_VARIATE", 50000, 2, {}),
            ("CALL", "SOBOL", 65536, 1, {}), ("CALL", "SOBOL", 16384, 4, {}), ("CALL", "PLAIN", 50000, 1, {"strike": 130.0, "sigma": 0.35})]
    for opt, meth, N, m, extra in runs:
        inp = {**base, "option": opt, "paths": N, "steps": m, "method": meth, **extra}
        price, se = mc_replay(inp)
        true = bs(opt, inp["spot"], inp["strike"], inp["r"], inp["q"], inp["sigma"], inp["t"])[0]
        err = abs(price - float(true))
        note(f"mc {opt} {meth} N={N} m={m}: price {price:.6f} true {float(true):.6f} err {err:.2e} stderr {se:.5f}")
        chk = {"output": "price", "expected": f(true), "method": "confidence_interval", "stderr_output": "stderr", "z": 4.0}
        if meth == "SOBOL":
            assert err < 0.02
            chk = {"output": "price", "expected": f(true), "method": "absolute", "limit": 0.02}
        else:
            assert err <= 4 * se
        s.add(op, inp, {"price": price, "stderr": se}, cls="common_rng", verified=["independent-replay", "analytic-mpmath-50"], extra_checks=[chk])
    s.add(op, {**base, "option": "CALL", "paths": 1, "method": "PLAIN"}, error="E_INPUT", tags=["invalid"])
    s.add(op, {**base, "option": "CALL", "paths": 10, "method": "PLAIN", "sigma": 0.0}, error="E_DOMAIN", tags=["invalid"])
    s.add(op, {**base, "option": "CALL", "paths": 10, "steps": 65, "method": "SOBOL"}, error="E_INPUT", tags=["invalid"])
    s.write()


def main():
    rng()
    sobol()
    monte_carlo()


if __name__ == "__main__":
    main()
