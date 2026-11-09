//! Sobol sequence (`sobol.md`).
use crate::error::{Result, fail};
use crate::json::{Json, parse};

const TABLE: &str =
    include_str!("../../../../specifications/01-core/data/sobol-joe-kuo-d6-64.json");

pub const MAX_DIMENSIONS: usize = 64;

/// Direction integers `v[1..=32]` for each of the first `dimensions` dimensions.
fn directions(dimensions: usize) -> Vec<[u32; 33]> {
    let (doc, _) = parse(TABLE).expect("embedded Sobol table is valid JSON");
    let rows = doc
        .get("dimensions")
        .and_then(Json::as_array)
        .expect("embedded Sobol table has dimensions");
    let mut out = Vec::with_capacity(dimensions);
    for row in rows.iter().take(dimensions) {
        let int = |k: &str| row.get(k).and_then(Json::as_int).expect("table integer");
        let s = int("s") as usize;
        let a = int("a") as u32;
        let m: Vec<u32> = row
            .get("m")
            .and_then(Json::as_array)
            .expect("table m")
            .iter()
            .map(|x| x.as_int().expect("table m value") as u32)
            .collect();
        let mut v = [0u32; 33];
        if int("d") == 1 {
            for k in 1..=32 {
                v[k] = 1u32 << (32 - k);
            }
        } else {
            for k in 1..=s.min(32) {
                v[k] = m[k - 1] << (32 - k);
            }
            for k in s + 1..=32 {
                v[k] = v[k - s] ^ (v[k - s] >> s);
                for j in 1..s {
                    if (a >> (s - 1 - j)) & 1 == 1 {
                        v[k] ^= v[k - j];
                    }
                }
            }
        }
        out.push(v);
    }
    out
}

#[derive(Debug)]
pub struct Sobol {
    v: Vec<[u32; 33]>,
    x: Vec<u32>,
    index: u64,
}

impl Sobol {
    /// Positioned so that the first `next_point` gives index `skip + 1`.
    pub fn new(dimensions: usize, skip: u64) -> Sobol {
        let v = directions(dimensions);
        let gray = skip ^ (skip >> 1);
        let x = v
            .iter()
            .map(|vd| {
                (0..32)
                    .filter(|b| (gray >> b) & 1 == 1)
                    .fold(0u32, |acc, b| acc ^ vd[b + 1])
            })
            .collect();
        Sobol { v, x, index: skip }
    }

    /// Unchecked kernel (E1): inputs are not validated, and NaN or infinity in gives NaN out.
    pub fn next_point(&mut self, out: &mut [f64]) {
        let c = (!self.index).trailing_zeros() as usize + 1;
        self.index += 1;
        for d in 0..self.x.len() {
            self.x[d] ^= self.v[d][c];
            out[d] = f64::from(self.x[d]) * 2f64.powi(-32);
        }
    }
}

pub fn points(dimensions: i64, count: i64, skip: i64) -> Result<Vec<Vec<f64>>> {
    if dimensions < 1 || dimensions > MAX_DIMENSIONS as i64 {
        return fail("E_INPUT", "dimensions must be 1 to 64");
    }
    if count < 1 {
        return fail("E_INPUT", "count must be at least 1");
    }
    if skip < 0 || skip + count >= 1i64 << 32 {
        return fail("E_INPUT", "indices must stay below 2^32");
    }
    let mut g = Sobol::new(dimensions as usize, skip as u64);
    let mut out = Vec::with_capacity(count as usize);
    for _ in 0..count {
        let mut p = vec![0.0; dimensions as usize];
        g.next_point(&mut p);
        out.push(p);
    }
    Ok(out)
}
