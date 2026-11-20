# notes (tlk_k v2 blind lane)

Value source: independent exact integer arithmetic (stdlib only). q = c exactly (Fraction(c) = A/2^k), p = 1-q = a/2^k;
P(X<=x) = A^(n-x) * T / 2^(kn), T = sum_{i<=x} C(n,i) a^i A^(x-i) (recurrence R_{j+1}=R_j*A + C_{j+1}a^{j+1}), rounded once
to binary64 (half-even, own sticky rounding). No floating-point algorithm of KR-237 was used; the ruling's algorithm was not
reimplemented, only the target value (spec section risk.backtest.traffic_light, KR-253 amendment) was used. Whole run ~5 min.

Ambiguities / assumptions:
- Zone compared on the rounded binary64 P against binary64 0.95 and 0.9999 ("below" = strict <). Cases 0016, 0017, 0018:
  n=1, x=0, P = c exactly, so P equals the threshold float in 0016 (0.95 -> YELLOW) and 0018 (0.9999 -> RED); 0017 (0.99) is YELLOW.
  Whether the threshold means the real number 0.95 rather than binary64 0.95 is not stated; I assumed binary64 literals (tie => not below).
- plus_factor: only n=250, c=0.99 (cases 0019: x=5 -> 0.4; 0020: x=0 -> 0); null elsewhere, including n=1 cases.
- Cases 0014 (x=10164, P=0.9506 -> YELLOW) and 0012/0013 need no special reading.
