//! A port of `numpy.random.default_rng(seed)` for integer seeds below 2^32: `SeedSequence`, PCG64
//! (XSL-RR 128/64) and the `Generator` draws the micro-estimator recovery tests use (HR-71 ties the
//! spec's seeds to this generator). Ported from the Java test port (`NumpyRng.java`), itself from
//! numpy's `bit_generator.pyx`, `pcg64.h` and `distributions.c`; checked draw by draw against the
//! values numpy printed (`micro_est_recovery.rs`).
#![allow(dead_code, clippy::excessive_precision)]

mod tables;
use tables::{FE_DOUBLE, FI_DOUBLE, KE_DOUBLE, KI_DOUBLE, WE_DOUBLE, WI_DOUBLE};

const MUL: u128 = (0x2360_ED05_1FC6_5DA4_u128 << 64) | 0x4385_DF64_9FCC_F645;
const NOR_R: f64 = 3.6541528853610087963519472518;
const NOR_INV_R: f64 = 0.27366123732975827203338247596;
const EXP_R: f64 = 7.6971174701310497140446280481;

pub struct NumpyRng {
    state: u128,
    inc: u128,
    u32: Option<u32>,
}

fn hashmix(value: u32, hc: &mut u32) -> u32 {
    let mut v = value ^ *hc;
    *hc = hc.wrapping_mul(0x931e_8875);
    v = v.wrapping_mul(*hc);
    v ^ (v >> 16)
}

fn mix(x: u32, y: u32) -> u32 {
    let r = 0xca01_f9dd_u32
        .wrapping_mul(x)
        .wrapping_sub(0x4973_f715_u32.wrapping_mul(y));
    r ^ (r >> 16)
}

/// `SeedSequence(seed).generate_state(4, uint64)` for a one-word entropy and a pool of 4 words.
pub fn seed_sequence(seed: u32) -> [u64; 4] {
    let mut hc = 0x43b0_d7e5_u32;
    let mut mixer = [0u32; 4];
    for (i, m) in mixer.iter_mut().enumerate() {
        *m = hashmix(if i == 0 { seed } else { 0 }, &mut hc);
    }
    for src in 0..4 {
        for dst in 0..4 {
            if src != dst {
                let h = hashmix(mixer[src], &mut hc);
                mixer[dst] = mix(mixer[dst], h);
            }
        }
    }
    let mut h = 0x8b51_f9dd_u32;
    let mut out = [0u64; 4];
    for i in 0..8 {
        let mut v = mixer[i % 4];
        v ^= h;
        h = h.wrapping_mul(0x58f3_8ded);
        v = v.wrapping_mul(h);
        v ^= v >> 16;
        out[i / 2] |= u64::from(v) << (32 * (i % 2));
    }
    out
}

impl NumpyRng {
    pub fn new(seed: u32) -> NumpyRng {
        let w = seed_sequence(seed);
        let initstate = (u128::from(w[0]) << 64) | u128::from(w[1]);
        let initseq = (u128::from(w[2]) << 64) | u128::from(w[3]);
        // pcg_setseq_128_srandom_r: inc = (initseq << 1) | 1; state = 0; step; state += initstate; step
        let mut r = NumpyRng {
            state: 0,
            inc: (initseq << 1) | 1,
            u32: None,
        };
        r.step();
        r.state = r.state.wrapping_add(initstate);
        r.step();
        r
    }

    fn step(&mut self) {
        self.state = self.state.wrapping_mul(MUL).wrapping_add(self.inc);
    }

    /// `bit_generator.random_raw()`.
    pub fn next_u64(&mut self) -> u64 {
        self.step();
        let (hi, lo) = ((self.state >> 64) as u64, self.state as u64);
        (hi ^ lo).rotate_right((hi >> 58) as u32)
    }

    /// numpy's buffered 32-bit draw: low half of a fresh 64-bit draw, then its high half.
    pub fn next_u32(&mut self) -> u32 {
        if let Some(v) = self.u32.take() {
            return v;
        }
        let n = self.next_u64();
        self.u32 = Some((n >> 32) as u32);
        n as u32
    }

    /// `random()`: 53 random bits over 2^53.
    pub fn random(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 * (1.0 / 9007199254740992.0)
    }

    /// `integers(low, high)` with high - low at most 2^32 - 1: Lemire's method on buffered draws.
    pub fn integers(&mut self, low: i64, high: i64) -> i64 {
        let rng = (high - low - 1) as u64;
        if rng == 0 {
            return low;
        }
        let excl = rng + 1;
        let mut m = u64::from(self.next_u32()) * excl;
        let mut left = m & 0xFFFF_FFFF;
        if left < excl {
            let threshold = (0xFFFF_FFFF - rng) % excl;
            while left < threshold {
                m = u64::from(self.next_u32()) * excl;
                left = m & 0xFFFF_FFFF;
            }
        }
        low + (m >> 32) as i64
    }

    /// `choice(values)` with replacement and no weights: `values[integers(0, n)]`.
    pub fn choice(&mut self, values: &[i64]) -> i64 {
        values[self.integers(0, values.len() as i64) as usize]
    }

    pub fn normal(&mut self, loc: f64, scale: f64) -> f64 {
        loc + scale * self.standard_normal()
    }

    pub fn exponential(&mut self, scale: f64) -> f64 {
        scale * self.standard_exponential()
    }

    pub fn standard_normal(&mut self) -> f64 {
        loop {
            let mut r = self.next_u64();
            let idx = (r & 0xff) as usize;
            r >>= 8;
            let rabs = (r >> 1) & 0x000f_ffff_ffff_ffff;
            let x = rabs as f64 * WI_DOUBLE[idx] * if r & 1 != 0 { -1.0 } else { 1.0 };
            if rabs < KI_DOUBLE[idx] {
                return x;
            }
            if idx == 0 {
                loop {
                    let xx = -NOR_INV_R * (-self.random()).ln_1p();
                    let yy = -(-self.random()).ln_1p();
                    if yy + yy > xx * xx {
                        return if (rabs >> 8) & 1 != 0 {
                            -(NOR_R + xx)
                        } else {
                            NOR_R + xx
                        };
                    }
                }
            }
            if (FI_DOUBLE[idx - 1] - FI_DOUBLE[idx]) * self.random() + FI_DOUBLE[idx]
                < (-0.5 * x * x).exp()
            {
                return x;
            }
        }
    }

    pub fn standard_exponential(&mut self) -> f64 {
        loop {
            let mut ri = self.next_u64() >> 3;
            let idx = (ri & 0xff) as usize;
            ri >>= 8;
            let x = ri as f64 * WE_DOUBLE[idx];
            if ri < KE_DOUBLE[idx] {
                return x;
            }
            if idx == 0 {
                return EXP_R - (-self.random()).ln_1p();
            }
            if (FE_DOUBLE[idx - 1] - FE_DOUBLE[idx]) * self.random() + FE_DOUBLE[idx] < (-x).exp() {
                return x;
            }
        }
    }

    /// `poisson(lam)` for lam at least 10 (PTRS, Hormann 1993), the only branch the tests reach.
    pub fn poisson(&mut self, lam: f64) -> i64 {
        assert!(lam >= 10.0, "only the PTRS branch (lam >= 10) is ported");
        let slam = lam.sqrt();
        let loglam = lam.ln();
        let b = 0.931 + 2.53 * slam;
        let a = -0.059 + 0.02483 * b;
        let invalpha = 1.1239 + 1.1328 / (b - 3.4);
        let vr = 0.9277 - 3.6224 / (b - 2.0);
        loop {
            let u = self.random() - 0.5;
            let v = self.random();
            let us = 0.5 - u.abs();
            let k = ((2.0 * a / us + b) * u + lam + 0.43).floor() as i64;
            if us >= 0.07 && v <= vr {
                return k;
            }
            if k < 0 || (us < 0.013 && v > us) {
                continue;
            }
            if v.ln() + invalpha.ln() - (a / (us * us) + b).ln()
                <= -lam + k as f64 * loglam - loggam(k as f64 + 1.0)
            {
                return k;
            }
        }
    }
}

const LG: [f64; 10] = [
    8.333333333333333e-02,
    -2.777777777777778e-03,
    7.936507936507937e-04,
    -5.952380952380952e-04,
    8.417508417508418e-04,
    -1.917526917526918e-03,
    6.410256410256410e-03,
    -2.955065359477124e-02,
    1.796443723688307e-01,
    -1.39243221690590e+00,
];

pub fn loggam(x: f64) -> f64 {
    if x == 1.0 || x == 2.0 {
        return 0.0;
    }
    let n = if x < 7.0 { (7.0 - x) as i64 } else { 0 };
    let mut x0 = x + n as f64;
    let x2 = (1.0 / x0) * (1.0 / x0);
    let mut gl0 = LG[9];
    for k in (0..9).rev() {
        gl0 *= x2;
        gl0 += LG[k];
    }
    let mut gl = gl0 / x0 + 0.5 * 1.8378770664093453e+00 + (x0 - 0.5) * x0.ln() - x0;
    for _ in 0..n {
        gl -= (x0 - 1.0).ln();
        x0 -= 1.0;
    }
    gl
}
