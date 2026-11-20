# Independent exact reference: plain stdlib, exact integer arithmetic. q = c exactly (binary64), p = 1 - q.
import json
from fractions import Fraction

def round_ratio(num, e):
    """Correctly rounded float of num / 2**e (num>0 int), half-even, sticky."""
    if num == 0: return 0.0
    bl = num.bit_length()
    shift = bl - 54
    if shift > 0:
        top = num >> shift
        sticky = (num & ((1 << shift) - 1)) != 0
    else:
        top = num << (-shift); sticky = False
    # top has 54 bits; round to 53 half-even with sticky
    low = top & 1; top >>= 1
    if low and (sticky or (top & 1)): top += 1
    # value = top * 2**(shift+1-e)
    ex = shift + 1 - e
    return float(Fraction(top) * (Fraction(2) ** ex))  # top<=2**53 exact, power of 2 exact

def cdf(n, x, c):
    q = Fraction(c)
    A, D = q.numerator, q.denominator          # q = A/D, D = 2**k
    k = D.bit_length() - 1
    assert D == 1 << k
    a = D - A                                   # p = a/D
    # P = sum_{i<=x} C(n,i) a^i A^(n-i) / D^n = A^(n-x) * T / D^n
    # T = sum_{i<=x} C(n,i) a^i A^(x-i), via R_{j+1} = R_j*A + C_{j+1} a^{j+1}
    if a == 0: return 1.0
    C = 1; ap = 1; R = 1 * 1  # j=0: C0*a^0*A^0
    for j in range(0, x):
        C = C * (n - j) // (j + 1)
        ap *= a
        R = R * A + C * ap
    num = pow(A, n - x) * R
    return round_ratio(num, k * n)

def zone(P):
    return "GREEN" if P < 0.95 else ("YELLOW" if P < 0.9999 else "RED")

PLUS = {5:0.40,6:0.50,7:0.65,8:0.75,9:0.85}
def plus(n, x, c):
    if n != 250 or c != 0.99: return None
    if x <= 4: return 0
    return PLUS.get(x, 1.00)

if __name__ == "__main__":
    import sys
    inp = json.load(open(sys.argv[1]))["cases"]
    out = {}
    for cid, d in inp.items():
        P = cdf(d["observations"], d["exceptions"], d["confidence"])
        out[cid] = {"cumulative_probability": P, "zone": zone(P),
                    "plus_factor": plus(d["observations"], d["exceptions"], d["confidence"])}
        print(cid, repr(P), out[cid]["zone"], flush=True)
    json.dump({"cases": out}, open(sys.argv[2], "w"), indent=1)
