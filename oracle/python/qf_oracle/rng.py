"""Independent replay of rng.md, sobol.md and Black-Scholes. Pure integer Python for the generator."""
import json
import math

import mpmath as mp

from .common import ROOT

M = (1 << 64) - 1


def rotl(x, k):
    return ((x << k) | (x >> (64 - k))) & M


def splitmix(state):
    while True:
        state = (state + 0x9E3779B97F4A7C15) & M
        z = state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & M
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & M
        yield z ^ (z >> 31)


class Xo:
    def __init__(self, seed=None, state=None, stream=0):
        if state is None:
            g = splitmix(seed)
            state = [next(g) for _ in range(4)]
        self.s = list(state)
        for _ in range(stream):
            self.jump()

    def next(self):
        s = self.s
        r = (rotl((s[1] * 5) & M, 7) * 9) & M
        t = (s[1] << 17) & M
        s[2] ^= s[0]
        s[3] ^= s[1]
        s[1] ^= s[2]
        s[0] ^= s[3]
        s[2] ^= t
        s[3] = rotl(s[3], 45)
        return r

    def jump(self):
        n = [0, 0, 0, 0]
        for w in (0x180EC6D33CFD0ABA, 0xD5A61266F0C9392C, 0xA9582618E03FC9AA, 0x39ABDC4529B1661C):
            for b in range(64):
                if (w >> b) & 1:
                    n = [a ^ c for a, c in zip(n, self.s)]
                self.next()
        self.s = n

    def uniform(self):
        return ((self.next() >> 12) + 0.5) * 2.0 ** -52


A = [3.387132872796366608, 133.14166789178437745, 1971.5909503065514427, 13731.693765509461125, 45921.953931549871457, 67265.770927008700853, 33430.575583588128105, 2509.0809287301226727]
B = [1.0, 42.313330701600911252, 687.18700749205790830, 5394.1960214247511077, 21213.794301586595867, 39307.895800092710610, 28729.085735721942674, 5226.4952788528545610]
C = [1.42343711074968357734, 4.63033784615654529590, 5.76949722146069140550, 3.64784832476320460504, 1.27045825245236838258, 0.241780725177450611770, 0.0227238449892691845833, 0.000774545014278341407640]
D = [1.0, 2.05319162663775882187, 1.67638483018380384940, 0.689767334985100004550, 0.148103976427480074590, 0.0151986665636164571966, 0.000547593808499534494600, 1.05075007164441684324e-9]
E = [6.65790464350110377720, 5.46378491116411436990, 1.78482653991729133580, 0.296560571828504891230, 0.0265321895265761230930, 0.00124266094738807843860, 0.0000271155556874348757815, 2.01033439929228813265e-7]
F = [1.0, 0.599832206555887937690, 0.136929880922735805310, 0.0148753612908506148525, 0.000786869131145613259100, 0.0000184631831751005468180, 1.42151175831644588870e-7, 2.04426310338993978564e-15]


def horner(c, r):
    v = 0.0
    for a in reversed(c):
        v = v * r + a
    return v


def ppnd16(p):
    q = p - 0.5
    if abs(q) <= 0.425:
        r = 0.180625 - q * q
        return q * horner(A, r) / horner(B, r)
    r = p if q < 0 else 1 - p
    r = math.sqrt(-math.log(r))
    if r <= 5:
        r -= 1.6
        v = horner(C, r) / horner(D, r)
    else:
        r -= 5
        v = horner(E, r) / horner(F, r)
    return -v if q < 0 else v


def true_inverse_normal(p):
    with mp.workdps(700):  # 2p - 1 must keep p's digits down to 1e-300
        return +(mp.sqrt(2) * mp.erfinv(2 * mp.mpf(p) - 1))


class Sobol:
    def __init__(self, dims):
        rows = json.loads((ROOT / "specifications/01-core/data/sobol-joe-kuo-d6-64.json").read_text())["dimensions"][:dims]
        self.v = []
        for row in rows:
            v = [0] * 33
            if row["d"] == 1:
                for k in range(1, 33):
                    v[k] = 1 << (32 - k)
            else:
                s, a, m = row["s"], row["a"], row["m"]
                for k in range(1, min(s, 32) + 1):
                    v[k] = m[k - 1] << (32 - k)
                for k in range(s + 1, 33):
                    v[k] = v[k - s] ^ (v[k - s] >> s)
                    for j in range(1, s):
                        if (a >> (s - 1 - j)) & 1:
                            v[k] ^= v[k - j]
            self.v.append(v)
        self.x = [0] * dims
        self.i = 0

    def next(self):
        c, n = 1, self.i
        while n & 1:
            n >>= 1
            c += 1
        for d, v in enumerate(self.v):
            self.x[d] ^= v[c]
        self.i += 1
        return [x * 2.0 ** -32 for x in self.x]


def bs(option, S, K, r, q, sig, t):
    S, K, r, q, sig, t = map(mp.mpf, (S, K, r, q, sig, t))
    N = lambda x: mp.erfc(-x / mp.sqrt(2)) / 2  # noqa: E731
    n = lambda x: mp.exp(-x * x / 2) / mp.sqrt(2 * mp.pi)  # noqa: E731
    d1 = (mp.log(S / K) + (r - q + sig * sig / 2) * t) / (sig * mp.sqrt(t))
    d2 = d1 - sig * mp.sqrt(t)
    dq, dr = mp.exp(-q * t), mp.exp(-r * t)
    gamma = dq * n(d1) / (S * sig * mp.sqrt(t))
    if option == "CALL":
        return S * dq * N(d1) - K * dr * N(d2), dq * N(d1), gamma
    return K * dr * N(-d2) - S * dq * N(-d1), -dq * N(-d1), gamma
