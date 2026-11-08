# Common random numbers

Spec version 1.0.0. Status: Specified. Referenced by `conformance/tolerances/policy.yaml`.

Monte Carlo can only be compared tightly across languages if all four draw the same numbers. So the
generator is fixed here, down to the bit, and is implemented in each language from this page. A
language's own random library is not used for conformance.

All integer arithmetic is on unsigned 64 bits and wraps. In Java use `long`, `>>>`, and
`Long.toUnsignedString`. In Python mask with `2^64 - 1`.

## Seeding: SplitMix64

```
next(): state += 0x9E3779B97F4A7C15
        z = state
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9
        z = (z ^ (z >> 27)) * 0x94D049BB133111EB
        return z ^ (z >> 31)
```

Start from `state = seed`. The four words `s[0..3]` of the main generator are the first four outputs.

## Generator: xoshiro256**

```
next(): result = rotl(s[1] * 5, 7) * 9
        t = s[1] << 17
        s[2] ^= s[0];  s[3] ^= s[1];  s[1] ^= s[2];  s[0] ^= s[3]
        s[2] ^= t
        s[3] = rotl(s[3], 45)
        return result
```

## Streams

Stream `k` (0 to 1023) is the seeded state advanced by `k` jumps. A jump moves the generator on by
2^128 steps:

```
J = 0x180EC6D33CFD0ABA, 0xD5A61266F0C9392C, 0xA9582618E03FC9AA, 0x39ABDC4529B1661C
n = 0,0,0,0
for each word w of J in order: for bit b from 0 to 63:
    if w has bit b set: n ^= s  (word by word)
    next()
s = n
```

## Uniforms

`u = ((x >> 12) + 0.5) * 2^-52`, with `x` one generator output. `x >> 12` has 52 bits, so the sum
and the product are exact. `u` lies in `[2^-53, 1 - 2^-53]`, never 0 or 1, and is bit-identical in all
four languages.

## Normals: inverse transform by AS 241

`z = PPND16(u)`, Wichura's algorithm AS 241, one uniform per normal. It is chosen over Box-Muller and
ziggurat because it uses one uniform each, keeps draws in step, and also serves Sobol.
It uses only `log`, `sqrt` and rational functions, so languages agree to a few ulps, not to the bit.

```
q = p - 0.5
if |q| <= 0.425:
    r = 0.180625 - q*q
    return q * A(r) / B(r)
r = p if q < 0 else 1 - p
r = sqrt(-log(r))
if r <= 5:  r -= 1.6;  v = C(r) / D(r)
else:       r -= 5;    v = E(r) / F(r)
return -v if q < 0 else v
```

`A`..`F` are polynomials in `r`, lowest power first, evaluated by Horner:

```
A: 3.387132872796366608, 133.14166789178437745, 1971.5909503065514427, 13731.693765509461125,
   45921.953931549871457, 67265.770927008700853, 33430.575583588128105, 2509.0809287301226727
B: 1, 42.313330701600911252, 687.18700749205790830, 5394.1960214247511077,
   21213.794301586595867, 39307.895800092710610, 28729.085735721942674, 5226.4952788528545610
C: 1.42343711074968357734, 4.63033784615654529590, 5.76949722146069140550, 3.64784832476320460504,
   1.27045825245236838258, 0.241780725177450611770, 0.0227238449892691845833, 0.000774545014278341407640
D: 1, 2.05319162663775882187, 1.67638483018380384940, 0.689767334985100004550,
   0.148103976427480074590, 0.0151986665636164571966, 0.000547593808499534494600, 1.05075007164441684324e-9
E: 6.65790464350110377720, 5.46378491116411436990, 1.78482653991729133580, 0.296560571828504891230,
   0.0265321895265761230930, 0.00124266094738807843860, 0.0000271155556874348757815, 2.01033439929228813265e-7
F: 1, 0.599832206555887937690, 0.136929880922735805310, 0.0148753612908506148525,
   0.000786869131145613259100, 0.0000184631831751005468180, 1.42151175831644588870e-7, 2.04426310338993978564e-15
```

The oracle holds these constants against 50-digit `erfinv`: relative error below 1e-15 over the
tested range of `p`.

## Operations

`core.rng.next_u64`. Inputs: `seed` (u64 string), `stream` (integer), `count` (at least 1), optional
`skip` (default 0, draws thrown away first). Upper limits are in `limits.md`. Output: `values`, u64 strings.

`core.rng.uniforms`. Same inputs. Output: `values`, reals. Compared exactly (class `bit_exact`).

`core.rng.normals`. Same inputs. Output: `values`, `PPND16` of the uniforms.

`core.rng.inverse_normal`. Input: `p`, an array of reals. Output: `z`. Any `p` outside `(0, 1)` is
`E_DOMAIN`.

`core.rng.set_state_next_u64`. Inputs: `state`, four u64 strings, and `count`. Output: `values`. It
exists so that the published reference vectors can be run directly. All-zero state is `E_INPUT`.

A `seed` that is not a decimal u64 string, or a `stream` out of range, or a `count` below 1, is `E_SCHEMA`.

## Acceptance

Integers and uniforms: exact. Normals: class `common_rng`. Oracle: pure integer Python, checked
against published reference outputs carried in the `rand_xoshiro` 0.7.0 tests, which those tests
state were produced by the authors' reference C code, and the SplitMix64 vector from the same place.
No published jump vector was found, so jump results rest on the oracle's own code.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Steele, G. L., Lea, D. and Flood, C. H., "Fast splittable pseudorandom number generators", OOPSLA 2014 (SplitMix64) (not opened)
- [S2] Blackman, D. and Vigna, S., "Scrambled linear pseudorandom number generators", *ACM Transactions on Mathematical Software* 47(4), 2021 (xoshiro256**, jump function); reference C code at prng.di.unimi.it (reference-code page opened 2026-11-07: xoshiro256** code and SplitMix seeding confirmed; paper details not opened)
- [S3] Wichura, M. J., "Algorithm AS 241: The percentage points of the normal distribution", *Applied Statistics* 37(3), 1988, 477-484 (PPND16) (not opened)
- [S4] Glasserman, P., *Monte Carlo Methods in Financial Engineering*, Springer, 2003, chapter 2 (generating random numbers and random variables) (not opened)
