//! Common random numbers (`rng.md`).
use crate::error::{Result, fail};

pub fn splitmix64(state: &mut u64) -> u64 {
    *state = state.wrapping_add(0x9E3779B97F4A7C15);
    let mut z = *state;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
    z ^ (z >> 31)
}

const JUMP: [u64; 4] = [
    0x180EC6D33CFD0ABA,
    0xD5A61266F0C9392C,
    0xA9582618E03FC9AA,
    0x39ABDC4529B1661C,
];

#[derive(Debug, Clone)]
pub struct Xoshiro {
    s: [u64; 4],
}

impl Xoshiro {
    pub fn from_state(s: [u64; 4]) -> Xoshiro {
        Xoshiro { s }
    }

    pub fn seeded(seed: u64, stream: u32) -> Xoshiro {
        let mut st = seed;
        let mut s = [0; 4];
        for w in &mut s {
            *w = splitmix64(&mut st);
        }
        let mut g = Xoshiro { s };
        for _ in 0..stream {
            g.jump();
        }
        g
    }

    pub fn next_u64(&mut self) -> u64 {
        let s = &mut self.s;
        let result = s[1].wrapping_mul(5).rotate_left(7).wrapping_mul(9);
        let t = s[1] << 17;
        s[2] ^= s[0];
        s[3] ^= s[1];
        s[1] ^= s[2];
        s[0] ^= s[3];
        s[2] ^= t;
        s[3] = s[3].rotate_left(45);
        result
    }

    pub fn jump(&mut self) {
        let mut n = [0u64; 4];
        for w in JUMP {
            for b in 0..64 {
                if (w >> b) & 1 == 1 {
                    for i in 0..4 {
                        n[i] ^= self.s[i];
                    }
                }
                self.next_u64();
            }
        }
        self.s = n;
    }

    pub fn next_uniform(&mut self) -> f64 {
        to_uniform(self.next_u64())
    }

    pub fn next_normal(&mut self) -> f64 {
        ppnd16(self.next_uniform())
    }
}

pub fn to_uniform(x: u64) -> f64 {
    ((x >> 12) as f64 + 0.5) * 2f64.powi(-52)
}

fn horner(c: &[f64; 8], r: f64) -> f64 {
    c.iter().rev().fold(0.0, |acc, k| acc * r + k)
}

const A: [f64; 8] = [
    3.387132872796366608,
    133.14166789178437745,
    1971.5909503065514427,
    13731.693765509461125,
    45921.953931549871457,
    67265.770927008700853,
    33430.575583588128105,
    2509.0809287301226727,
];
const B: [f64; 8] = [
    1.0,
    42.313330701600911252,
    687.18700749205790830,
    5394.1960214247511077,
    21213.794301586595867,
    39307.895800092710610,
    28729.085735721942674,
    5226.4952788528545610,
];
const C: [f64; 8] = [
    1.42343711074968357734,
    4.63033784615654529590,
    5.76949722146069140550,
    3.64784832476320460504,
    1.27045825245236838258,
    0.241780725177450611770,
    0.0227238449892691845833,
    0.000774545014278341407640,
];
const D: [f64; 8] = [
    1.0,
    2.05319162663775882187,
    1.67638483018380384940,
    0.689767334985100004550,
    0.148103976427480074590,
    0.0151986665636164571966,
    0.000547593808499534494600,
    1.05075007164441684324e-9,
];
const E: [f64; 8] = [
    6.65790464350110377720,
    5.46378491116411436990,
    1.78482653991729133580,
    0.296560571828504891230,
    0.0265321895265761230930,
    0.00124266094738807843860,
    0.0000271155556874348757815,
    2.01033439929228813265e-7,
];
const F: [f64; 8] = [
    1.0,
    0.599832206555887937690,
    0.136929880922735805310,
    0.0148753612908506148525,
    0.000786869131145613259100,
    0.0000184631831751005468180,
    1.42151175831644588870e-7,
    2.04426310338993978564e-15,
];

/// Wichura's AS 241 inverse normal, for `p` strictly inside (0, 1).
pub fn ppnd16(p: f64) -> f64 {
    let q = p - 0.5;
    if q.abs() <= 0.425 {
        let r = 0.180625 - q * q;
        return q * horner(&A, r) / horner(&B, r);
    }
    let r = if q < 0.0 { p } else { 1.0 - p };
    let r = (-r.ln()).sqrt();
    let v = if r <= 5.0 {
        let r = r - 1.6;
        horner(&C, r) / horner(&D, r)
    } else {
        let r = r - 5.0;
        horner(&E, r) / horner(&F, r)
    };
    if q < 0.0 { -v } else { v }
}

pub fn inverse_normal(p: &[f64]) -> Result<Vec<f64>> {
    if p.iter().any(|&v| v <= 0.0 || v >= 1.0) {
        return fail("E_DOMAIN", "p must lie in (0, 1)");
    }
    Ok(p.iter().map(|&v| ppnd16(v)).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generators_are_deterministic_and_streams_differ() {
        let (mut a, mut b, mut c) = (
            Xoshiro::seeded(7, 0),
            Xoshiro::seeded(7, 0),
            Xoshiro::seeded(7, 1),
        );
        let xs: Vec<u64> = (0..16).map(|_| a.next_u64()).collect();
        let ys: Vec<u64> = (0..16).map(|_| b.next_u64()).collect();
        let zs: Vec<u64> = (0..16).map(|_| c.next_u64()).collect();
        assert_eq!(xs, ys);
        assert_ne!(xs, zs);
        let mut s = 0;
        assert_ne!(splitmix64(&mut s), splitmix64(&mut s));
    }

    #[test]
    fn uniforms_lie_in_open_interval_with_sane_moments() {
        let mut g = Xoshiro::seeded(42, 3);
        let n = 20_000;
        let (mut m, mut v) = (0.0, 0.0);
        for _ in 0..n {
            let u = g.next_uniform();
            assert!(u > 0.0 && u < 1.0);
            let z = g.next_normal();
            m += z;
            v += z * z;
        }
        let m = m / f64::from(n);
        assert!(m.abs() < 0.05, "{m}");
        assert!((v / f64::from(n) - 1.0).abs() < 0.05);
        assert!(to_uniform(0) > 0.0 && to_uniform(u64::MAX) < 1.0);
    }

    #[test]
    fn inverse_normal_is_odd_and_validates() {
        assert_eq!(ppnd16(0.5), 0.0);
        for p in [0.001, 1e-4, 0.02, 0.3, 0.45] {
            assert!((ppnd16(p) + ppnd16(1.0 - p)).abs() < 1e-9);
        }
        assert!((ppnd16(0.975) - 1.959963984540054).abs() < 1e-12);
        assert!(inverse_normal(&[0.0]).is_err());
        assert!(inverse_normal(&[1.0]).is_err());
        assert_eq!(inverse_normal(&[0.5, 0.5]).unwrap(), vec![0.0, 0.0]);
    }

    #[test]
    fn jump_moves_the_sequence() {
        let mut a = Xoshiro::seeded(1, 0);
        let mut b = a.clone();
        b.jump();
        assert_ne!(a.next_u64(), b.next_u64());
    }
}
