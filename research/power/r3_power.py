"""Pass probability of the amended R3 pass rule, by simulation. numpy only, seeded.

Amendment-1 rule, condition (1), for one study:
    SR0  = SE * E[max of N standard normals]          (deflation benchmark, N = family trial count 24)
    p    = 1 - Phi((SR_hat - SR0) / SE)               (one-sided; DSR = 1 - p)
    pass if p <= alpha_i, where alpha_i is the Holm level of the study among the three R3 studies:
    0.05/3 if it has the smallest p, 0.05/2 if second, 0.05 if last. The simulation reports both ends.
Equivalently: the one-sided lower (1 - alpha_i) confidence bound of the deflated Sharpe, SR_hat - SR0,
is above 0. Condition (3), same positive sign in each third of the holdout, is applied too.
Condition (2), positive at 2x costs, needs turnover that is unknown before the data is read, so the
simulated returns are net returns at 1x and condition (2) is not simulated (it can only lower the
pass probability).

SE methods, as preregistered:
  R3-01: Lo (2002) annualisation with the autocorrelation adjustment, 20 lags, daily returns.
  R3-02: stationary block bootstrap, mean block 3 months, monthly returns (B_BOOT draws here for
         speed; the study itself uses 10,000).
  R3-03: Lo (2002) with 3 lags, monthly returns.

Returns are Gaussian AR(1) with coefficient phi; phi = 0 is the headline, phi = 0.2 a stress for size.
True SR values are annualised.
"""
import math

import numpy as np

Z95 = 1.6448536269514722
Z975 = 1.959963984540054
GAMMA = 0.5772156649015329
FAMILY_TRIALS = 24
B_BOOT = 400
SEED = 20261109

STUDIES = {
    # id: (holdout years, periods per year, SE method, lags or mean block, MDS from the prereg)
    "R3-01": (13.83, 252, "lo", 20, 0.67),
    "R3-02": (3.83, 12, "boot", 3, 1.27),
    "R3-03": (10.83, 12, "lo", 3, 0.76),
}


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p):
    """Inverse normal CDF: Acklam's rational approximation refined by one Newton step."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    if p > 0.97575:
        return -norm_ppf(1.0 - p)
    if p < 0.02425:
        q = math.sqrt(-2.0 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    else:
        q = p - 0.5
        r = q * q
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    return x - (norm_cdf(x) - p) * math.sqrt(2.0 * math.pi) * math.exp(x * x / 2.0)


def expected_max_z(n):
    """Bailey and Lopez de Prado (2014): E[max of n iid N(0,1)] ~ (1-g) Phi^-1(1-1/n) + g Phi^-1(1-1/(n e))."""
    if n < 1:
        raise ValueError("trial count must be at least 1")
    if n == 1:
        return 0.0
    return (1 - GAMMA) * norm_ppf(1 - 1 / n) + GAMMA * norm_ppf(1 - 1 / (n * math.e))


def simulate_returns(rng, sims, n, sr_ann, q, phi=0.0):
    """Gaussian AR(1) per-period returns, unit marginal variance, annualised Sharpe sr_ann."""
    e = rng.standard_normal((sims, n))
    x = np.empty_like(e)
    x[:, 0] = e[:, 0]
    s = math.sqrt(1 - phi * phi)
    for t in range(1, n):
        x[:, t] = phi * x[:, t - 1] + s * e[:, t]
    return x + sr_ann / math.sqrt(q)


def lo_sharpe(x, q, lags):
    """Annualised Sharpe and SE, Lo (2002): eta = q / sqrt(q + 2 sum_{k=1..min(lags,q-1)} (q-k) rho_k)."""
    n = x.shape[1]
    mu = x.mean(axis=1)
    sr = mu / x.std(axis=1, ddof=1)
    xc = x - mu[:, None]
    var = (xc * xc).sum(axis=1)
    acc = np.zeros(x.shape[0])
    for k in range(1, min(lags, q - 1) + 1):
        acc += (q - k) * (xc[:, k:] * xc[:, :-k]).sum(axis=1) / var
    eta = q / np.sqrt(np.maximum(q + 2 * acc, 1e-12))
    return sr * eta, np.sqrt((1 + 0.5 * sr * sr) / n) * eta


def boot_sharpe(x, q, mean_block, rng, draws=B_BOOT, chunk=50):
    """Annualised Sharpe and its stationary block bootstrap SE (Politis and Romano 1994)."""
    sims, n = x.shape
    sr = x.mean(axis=1) / x.std(axis=1, ddof=1) * math.sqrt(q)
    se = np.empty(sims)
    for i in range(0, sims, chunk):
        start = rng.integers(0, n, size=(draws, n))
        new = rng.random((draws, n)) < 1.0 / mean_block
        idx = np.empty((draws, n), dtype=np.int64)
        idx[:, 0] = start[:, 0]
        for t in range(1, n):
            idx[:, t] = np.where(new[:, t], start[:, t], (idx[:, t - 1] + 1) % n)
        xb = x[i:i + chunk][:, idx]
        se[i:i + chunk] = (xb.mean(axis=2) / xb.std(axis=2, ddof=1) * math.sqrt(q)).std(axis=1, ddof=1)
    return sr, se


def thirds_positive(x):
    n = x.shape[1]
    cuts = [0, n // 3, 2 * n // 3, n]
    ok = np.ones(x.shape[0], dtype=bool)
    for a, b in zip(cuts[:-1], cuts[1:]):
        ok &= x[:, a:b].mean(axis=1) > 0
    return ok


def pass_probability(study, sr_ann, sims=4000, seed=SEED, phi=0.0, trials=FAMILY_TRIALS):
    """(pass probability at Holm level 0.05, at Holm level 0.05/3) for one study."""
    years, q, method, lag, _ = STUDIES[study]
    n = int(round(years * q))
    rng = np.random.default_rng(seed)
    x = simulate_returns(rng, sims, n, sr_ann, q, phi)
    sr, se = lo_sharpe(x, q, lag) if method == "lo" else boot_sharpe(x, q, lag, rng)
    z = (sr - se * expected_max_z(trials)) / se
    stable = thirds_positive(x)
    return float(np.mean((z > Z95) & stable)), float(np.mean((z > norm_ppf(1 - 0.05 / 3)) & stable))


def forward_pass_probability(sr_true, holdout_sr, sims=20000, seed=SEED, days=250):
    """Forward-log rule: the 250-day SR has the holdout's sign, and its two-sided 95% CI (Lo, iid,
    daily) contains the holdout estimate."""
    rng = np.random.default_rng(seed)
    sr, se = lo_sharpe(rng.standard_normal((sims, days)) + sr_true / math.sqrt(252), 252, 0)
    return float(np.mean((np.sign(sr) == np.sign(holdout_sr)) & (np.abs(sr - holdout_sr) <= Z975 * se)))


def table(sims=4000, seed=SEED):
    rows = []
    for s, spec in STUDIES.items():
        for sr in (0.0, 0.5, spec[4]):
            rows.append((s, sr, 0.0) + pass_probability(s, sr, sims, seed))
        rows.append((s, 0.0, 0.2) + pass_probability(s, 0.0, sims, seed, phi=0.2))
    return rows


if __name__ == "__main__":
    print(f"family trials {FAMILY_TRIALS}, E[max z] = {expected_max_z(FAMILY_TRIALS):.4f}, seed {SEED}")
    print("study  true_SR  phi  pass(Holm 0.05)  pass(Holm 0.05/3)")
    for s, sr, phi, a, b in table():
        print(f"{s}  {sr:5.2f}  {phi:.1f}  {a:.4f}  {b:.4f}")
    for s, spec in STUDIES.items():
        m = spec[4]
        print(f"forward {s}: true = holdout = {m}: {forward_pass_probability(m, m):.4f}; true 0, holdout {m}: {forward_pass_probability(0.0, m):.4f}")
