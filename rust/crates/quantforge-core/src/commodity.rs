//! Commodity forward curves and storage carry (`commodity.md`).
use crate::curve::Curve;
use crate::dates::Date;
use crate::error::{Result, fail};

/// `cmdty.curve.forward`. Quotes and months are month indices.
pub fn commodity_forwards(
    quotes: &[(i64, f64)],
    seasonality: Option<&[f64]>,
    months: &[i64],
) -> Result<Vec<f64>> {
    if quotes.is_empty() || quotes.windows(2).any(|w| w[1].0 <= w[0].0) {
        return fail("E_INPUT", "quote months must strictly increase");
    }
    if quotes.iter().any(|q| q.1 <= 0.0) {
        return fail("E_DOMAIN", "a price is not positive");
    }
    if seasonality.is_some_and(|s| s.len() != 12) {
        return fail("E_INPUT", "seasonality needs 12 terms");
    }
    let sigma = |k: i64| seasonality.map_or(0.0, |s| s[k.rem_euclid(12) as usize]);
    let l: Vec<f64> = quotes.iter().map(|(k, p)| p.ln() - sigma(*k)).collect();
    let (first, last) = (quotes[0].0, quotes[quotes.len() - 1].0);
    months
        .iter()
        .map(|k| {
            if *k < first || *k > last {
                return fail("E_OUT_OF_RANGE", "month is outside the quoted range");
            }
            let i = quotes.partition_point(|q| q.0 <= *k).saturating_sub(1);
            let lk = if i + 1 >= quotes.len() {
                l[i]
            } else {
                let u = (k - quotes[i].0) as f64 / (quotes[i + 1].0 - quotes[i].0) as f64;
                (1.0 - u) * l[i] + u * l[i + 1]
            };
            Ok((lk + sigma(*k)).exp())
        })
        .collect()
}

/// `cmdty.storage.carry`: `(convenience_yields, carry_values, arbitrage)`.
pub fn storage_carry(
    funding: &Curve,
    forwards: &[(Date, f64)],
    u: f64,
) -> Result<(Vec<f64>, Vec<f64>, Vec<bool>)> {
    if forwards.len() < 2
        || forwards[0].0 <= funding.as_of
        || forwards.windows(2).any(|w| w[1].0 <= w[0].0)
    {
        return fail(
            "E_INPUT",
            "at least two forwards, dates increasing after as_of",
        );
    }
    if u < 0.0 {
        return fail("E_DOMAIN", "storage_cost must not be negative");
    }
    if forwards.iter().any(|f| f.1 <= 0.0) {
        return fail("E_DOMAIN", "a forward price is not positive");
    }
    let (mut ys, mut cs, mut arb) = (Vec::new(), Vec::new(), Vec::new());
    for w in forwards.windows(2) {
        let ((d0, f0), (d1, f1)) = (w[0], w[1]);
        let dt = (d1.serial() - d0.serial()) as f64 / 365.0;
        let (p0, p1) = (funding.discount(d0)?, funding.discount(d1)?);
        let r = (p0 / p1).ln() / dt;
        ys.push(r + u - (f1 / f0).ln() / dt);
        let c = p1 * f1 - p0 * f0 * (u * dt).exp();
        cs.push(c);
        arb.push(c > 0.0);
    }
    Ok((ys, cs, arb))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::curve::{Interpolation, curve_time};

    fn d(s: &str) -> Date {
        Date::parse(s).unwrap()
    }

    fn flat(r: f64) -> Curve {
        let as_of = d("2026-11-06");
        let p = d("2056-11-06");
        Curve::from_logs(
            as_of,
            Interpolation::LogLinearDf,
            &[p],
            &[-r * curve_time(as_of, p)],
        )
    }

    #[test]
    fn commodity_curve_and_carry() {
        let q = [(100, 3.0), (103, 3.3)];
        let s: Vec<f64> = (0..12).map(|i| f64::from(i) * 0.01).collect();
        let f = commodity_forwards(&q, Some(&s), &[100, 103]).unwrap();
        assert!((f[0] - 3.0).abs() < 1e-14 && (f[1] - 3.3).abs() < 1e-14);
        let mid = commodity_forwards(&q, None, &[101]).unwrap()[0];
        assert!((mid - (3.0f64.ln() * 2.0 / 3.0 + 3.3f64.ln() / 3.0).exp()).abs() < 1e-14);
        assert_eq!(
            commodity_forwards(&q, None, &[99]).unwrap_err().code,
            "E_OUT_OF_RANGE"
        );
        assert_eq!(
            commodity_forwards(&[q[1], q[0]], None, &[101])
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        assert_eq!(
            commodity_forwards(&[(1, 0.0)], None, &[1])
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
        assert_eq!(
            commodity_forwards(&q, Some(&s[..6]), &[101])
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        let c = flat(0.04);
        let fw = [(d("2026-12-15"), 75.0), (d("2027-12-15"), 70.0)];
        let (y, v, a) = storage_carry(&c, &fw, 0.02).unwrap();
        assert!(y[0] > 0.0 && v[0] < 0.0 && !a[0]);
        let up = [(d("2026-12-15"), 70.0), (d("2027-12-15"), 80.0)];
        assert!(storage_carry(&c, &up, 0.0).unwrap().2[0]);
        assert_eq!(
            storage_carry(&c, &fw[..1], 0.02).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(storage_carry(&c, &fw, -0.01).unwrap_err().code, "E_DOMAIN");
    }
}
