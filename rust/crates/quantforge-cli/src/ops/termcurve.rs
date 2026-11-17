//! Stage J curves lane operations (rulings J-C-1 to J-C-9): the financing term structure
//! (`repo.term.curve`, `eq.forward.term_financed`) and the liquidity curve (`liq.curve.cost`).
//! Each domain has its own registry, as `ops/mod.rs` requires.
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::Result;
use quantforge_core::json::obj;
use quantforge_core::term_curves as tc;

/// Reads the six curve arrays, then gates: call it after reading every other key.
fn curve(i: &Inputs) -> Result<tc::FinancingCurve> {
    let (ft, fz) = (i.reals("funding_times")?, i.reals("funding_zero_rates")?);
    let (qt, qr) = (i.reals("quote_times")?, i.reals("repo_rates")?);
    let (bt, bf) = (i.reals("borrow_times")?, i.reals("borrow_fees")?);
    i.gate()?;
    tc::FinancingCurve::build(&ft, &fz, &qt, &qr, &bt, &bf)
}

pub mod repo {
    use super::{Inputs, Outcome, Result, curve, obj, plain, tc};

    super::super::registry! {
    (op, i)
        "repo.term.curve" => {
            let q = i.reals("query_times")?;
            let c = curve(i)?;
            let r = tc::term_curve(&c, &q)?;
            plain(obj([
                ("pillar_spreads", r.pillar_spreads.into()),
                ("spread", r.spread.into()),
                ("financing_df", r.financing_df.into()),
                ("financing_rate", r.financing_rate.into()),
                ("forward_financing", r.forward_financing.into()),
                ("borrow_fee", r.borrow_fee.into()),
            ]))
        },
    }
}

pub mod eq {
    use super::{Inputs, Outcome, Result, curve, obj, plain, tc};

    super::super::registry! {
    (op, i)
        "eq.forward.term_financed" => {
            let (s, t) = (i.f64("spot")?, i.f64("maturity_years")?);
            let (dt, da) = (i.reals("dividend_times")?, i.reals("dividend_amounts")?);
            let c = curve(i)?;
            let r = tc::forward_term_financed(&c, s, t, &dt, &da)?;
            plain(obj([
                ("forward", r.forward.into()),
                ("carry", r.carry.into()),
                ("carry_factor", r.carry_factor.into()),
                ("financing_df", r.financing_df.into()),
                ("pv_dividends", r.pv_dividends.into()),
            ]))
        },
    }
}

pub mod liq {
    use super::{Inputs, Outcome, Result, obj, plain, tc};

    super::super::registry! {
    (op, i)
        "liq.curve.cost" => {
            let p = tc::LiquidityParams {
                half_spread_bps: i.f64("half_spread_bps")?,
                daily_volume: i.f64("daily_volume")?,
                daily_vol: i.f64("daily_vol")?,
                coefficient: i.f64_or("coefficient", 1.0)?,
                exponent: i.f64_or("exponent", 0.5)?,
                risk_multiplier: i.f64_or("risk_multiplier", 0.0)?,
            };
            let (q, h) = (i.reals("sizes")?, i.reals("horizons_days")?);
            i.gate()?;
            let r = tc::liquidity_cost(&p, &q, &h)?;
            plain(obj([
                ("spread_cost", r.spread_cost.into()),
                ("impact", r.impact.into()),
                ("timing_risk", r.timing_risk.into()),
                ("total_cost", r.total_cost.into()),
                ("optimal_horizon", r.optimal_horizon.into()),
                ("min_cost", r.min_cost.into()),
            ]))
        },
    }
}
