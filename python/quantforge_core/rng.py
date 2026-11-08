"""Common random numbers (specifications/01-core/rng.md)."""
import math
from collections.abc import Sequence

from .errors import QfError

MASK = (1 << 64) - 1
_JUMP = (0x180EC6D33CFD0ABA, 0xD5A61266F0C9392C, 0xA9582618E03FC9AA, 0x39ABDC4529B1661C)
_TWO_M52 = 2.0**-52

_A = (3.387132872796366608, 133.14166789178437745, 1971.5909503065514427, 13731.693765509461125,
      45921.953931549871457, 67265.770927008700853, 33430.575583588128105, 2509.0809287301226727)
_B = (1.0, 42.313330701600911252, 687.18700749205790830, 5394.1960214247511077,
      21213.794301586595867, 39307.895800092710610, 28729.085735721942674, 5226.4952788528545610)
_C = (1.42343711074968357734, 4.63033784615654529590, 5.76949722146069140550,
      3.64784832476320460504, 1.27045825245236838258, 0.241780725177450611770,
      0.0227238449892691845833, 0.000774545014278341407640)
_D = (1.0, 2.05319162663775882187, 1.67638483018380384940, 0.689767334985100004550,
      0.148103976427480074590, 0.0151986665636164571966, 0.000547593808499534494600,
      1.05075007164441684324e-9)
_E = (6.65790464350110377720, 5.46378491116411436990, 1.78482653991729133580,
      0.296560571828504891230, 0.0265321895265761230930, 0.00124266094738807843860,
      0.0000271155556874348757815, 2.01033439929228813265e-7)
_F = (1.0, 0.599832206555887937690, 0.136929880922735805310, 0.0148753612908506148525,
      0.000786869131145613259100, 0.0000184631831751005468180, 1.42151175831644588870e-7,
      2.04426310338993978564e-15)


def _rotl(x: int, k: int) -> int:
    return ((x << k) | (x >> (64 - k))) & MASK


def _splitmix_words(seed: int, count: int) -> list[int]:
    state = seed
    words = []
    for _ in range(count):
        state = (state + 0x9E3779B97F4A7C15) & MASK
        z = state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
        words.append(z ^ (z >> 31))
    return words


class Xoshiro256:
    def __init__(self, state: Sequence[int]):
        self.s = list(state)

    @classmethod
    def seeded(cls, seed: int, stream: int = 0) -> Xoshiro256:
        g = cls(_splitmix_words(seed, 4))
        _advance(g, stream << 128)  # stream jumps of 2^128 steps each
        return g

    def next_u64(self) -> int:
        s = self.s
        s0, s1, s2, s3 = s
        result = (_rotl((s1 * 5) & MASK, 7) * 9) & MASK
        t = (s1 << 17) & MASK
        s2 ^= s0
        s3 ^= s1
        s1 ^= s2
        s0 ^= s3
        s2 ^= t
        s[0], s[1], s[2], s[3] = s0, s1, s2, _rotl(s3, 45)
        return result

    def jump(self) -> None:
        n = [0, 0, 0, 0]
        for word in _JUMP:
            for b in range(64):
                if (word >> b) & 1:
                    for i in range(4):
                        n[i] ^= self.s[i]
                self.next_u64()
        self.s = n

    def uniform(self) -> float:
        return ((self.next_u64() >> 12) + 0.5) * _TWO_M52

    def normal(self) -> float:
        return ppnd16(self.uniform())

    def normals(self, count: int) -> list[float]:
        """`count` calls of normal(), with the state in locals: the same operations, faster."""
        s0, s1, s2, s3 = self.s
        mask, scale, ppnd = MASK, _TWO_M52, ppnd16
        out = []
        for _ in range(count):
            x = (s1 * 5) & mask
            result = ((((x << 7) | (x >> 57)) & mask) * 9) & mask
            t = (s1 << 17) & mask
            s2 ^= s0
            s3 ^= s1
            s1 ^= s2
            s0 ^= s3
            s2 ^= t
            s3 = ((s3 << 45) | (s3 >> 19)) & mask
            out.append(ppnd(((result >> 12) + 0.5) * scale))
        self.s = [s0, s1, s2, s3]
        return out


def _horner(coefficients: tuple[float, ...], r: float) -> float:
    value = 0.0
    for c in reversed(coefficients):
        value = value * r + c
    return value


def ppnd16(p: float) -> float:
    """Wichura's AS 241. p must lie in (0, 1)."""
    q = p - 0.5
    if abs(q) <= 0.425:
        r = 0.180625 - q * q
        return q * _horner(_A, r) / _horner(_B, r)
    r = p if q < 0 else 1 - p
    r = math.sqrt(-math.log(r))
    if r <= 5:
        r -= 1.6
        v = _horner(_C, r) / _horner(_D, r)
    else:
        r -= 5
        v = _horner(_E, r) / _horner(_F, r)
    return -v if q < 0 else v


def inverse_normal(ps: Sequence[float]) -> list[float]:
    for p in ps:
        if not 0 < p < 1:
            raise QfError("E_DOMAIN", f"p = {p} is outside (0, 1)", "p")
    return [ppnd16(p) for p in ps]


# Advancing by k steps. The xoshiro256 step is linear over GF(2), so advancing k steps is
# P(T) applied to the state, with P = x^k mod p and p the characteristic polynomial of T. That is
# how jump() works too; it gives the same state as k calls of next_u64, in about 256 steps.

def _min_poly() -> int:
    """p(x) as an int (bit i is the coefficient of x^i), by Berlekamp-Massey on 512 output bits."""
    g = Xoshiro256(_splitmix_words(1, 4))
    bits = []
    for _ in range(512):
        bits.append(g.s[0] & 1)
        g.next_u64()
    c, b, length, m = 1, 1, 0, 1  # connection polynomials, with bit i the coefficient of x^i
    for n, bit in enumerate(bits):
        d = bit
        for i in range(1, length + 1):
            d ^= ((c >> i) & 1) & bits[n - i]
        if d == 0:
            m += 1
        elif 2 * length <= n:
            c, b, length, m = c ^ (b << m), c, n + 1 - length, 1
        else:
            c ^= b << m
            m += 1
    if length != 256:  # never: the xoshiro256 polynomial is primitive of degree 256
        raise AssertionError(f"minimal polynomial of degree {length}")
    # c is the connection polynomial; its reverse is the characteristic polynomial.
    return int(format(c, "0257b")[::-1], 2)


_POLY: list[int] = []


def _x_power_mod(k: int) -> int:
    if not _POLY:
        _POLY.append(_min_poly())
    p, top = _POLY[0], 1 << 256
    r = 1
    for bit in format(k, "b"):
        # square r: spread its bits (a carry-less square), then reduce
        sq, i, x = 0, 0, r
        while x:
            if x & 1:
                sq |= 1 << (2 * i)
            x >>= 1
            i += 1
        r = sq
        if bit == "1":
            r <<= 1
        for j in range(r.bit_length() - 1, 255, -1):
            if (r >> j) & 1:
                r ^= p << (j - 256)
        assert r < top
    return r


def _advance(g: Xoshiro256, k: int) -> None:
    if k < 512:
        for _ in range(k):
            g.next_u64()
        return
    poly, n = _x_power_mod(k), [0, 0, 0, 0]
    for b in range(256):
        if (poly >> b) & 1:
            for i in range(4):
                n[i] ^= g.s[i]
        g.next_u64()
    g.s = n


def _advanced(seed: int, stream: int, skip: int) -> Xoshiro256:
    g = Xoshiro256(_splitmix_words(seed, 4))
    _advance(g, (stream << 128) + skip)  # a jump is 2^128 steps
    return g


def next_u64(seed: int, stream: int, count: int, skip: int = 0) -> list[int]:
    g = _advanced(seed, stream, skip)
    return [g.next_u64() for _ in range(count)]


def uniforms(seed: int, stream: int, count: int, skip: int = 0) -> list[float]:
    g = _advanced(seed, stream, skip)
    return [g.uniform() for _ in range(count)]


def normals(seed: int, stream: int, count: int, skip: int = 0) -> list[float]:
    g = _advanced(seed, stream, skip)
    return g.normals(count)


def set_state_next_u64(state: Sequence[int], count: int) -> list[int]:
    if not any(state):
        raise QfError("E_INPUT", "the all-zero state is not allowed", "state")
    g = Xoshiro256(state)
    return [g.next_u64() for _ in range(count)]
