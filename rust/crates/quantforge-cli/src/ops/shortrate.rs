//! `rates.shortrate.*` operations (stage G wave 1, partial: `zcb`).
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::Result;
use quantforge_core::error::fail;
use quantforge_core::json::obj;
use quantforge_core::shortrate::{HwCurve, Model, zcb};

super::registry! {
(op, i)
    "rates.shortrate.zcb" => {
        let model = i.str("model")?;
        let (a, sigma) = (i.f64("mean_reversion")?, i.f64("sigma")?);
        let r = i.f64("short_rate")?;
        let (t, mat) = (i.f64("t_years")?, i.f64("maturity_years")?);
        let curve = match model {
            "HULL_WHITE" => {
                let c = super::rates::sub(i, "curve")?;
                let (ts, ds) = (c.reals("times")?, c.reals("discount_factors")?);
                Some((ts, ds))
            }
            _ => None,
        };
        let b = match model {
            "VASICEK" | "CIR" => Some(i.f64("long_term_mean")?),
            _ => None,
        };
        i.gate()?;
        let hw;
        let m = match (model, b, curve) {
            ("VASICEK", Some(b), _) => Model::Vasicek { a, b, sigma },
            ("CIR", Some(b), _) => Model::Cir { a, b, sigma },
            ("HULL_WHITE", _, Some((ts, ds))) => {
                hw = HwCurve::new(&ts, &ds)?;
                Model::HullWhite { a, sigma, curve: &hw }
            }
            _ => return fail("E_INPUT", "model must be VASICEK, CIR or HULL_WHITE"),
        };
        let (p, z) = zcb(&m, r, t, mat)?;
        plain(obj([("discount_factor", p.into()), ("zero_rate", z.into())]))
    }
}
