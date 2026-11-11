//! `risk.mc.greeks` (stage G wave 3a, Q9 part 1).
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::{Result, fail};
use quantforge_core::json::obj;
use quantforge_core::mc_greeks::{GbmOption, Method, Payoff, mc_greeks};

super::registry! {
(op, i)
    "risk.mc.greeks" => {
        let payoff = match i.str("payoff")? {
            "CALL" => Payoff::Call,
            "PUT" => Payoff::Put,
            "DIGITAL_CALL" => Payoff::DigitalCall,
            _ => return fail("E_INPUT", "payoff must be CALL, PUT or DIGITAL_CALL"),
        };
        let method = i.str("method")?;
        if !matches!(method, "PATHWISE" | "LIKELIHOOD_RATIO" | "BUMP") {
            return fail("E_INPUT", "method must be PATHWISE, LIKELIHOOD_RATIO or BUMP");
        }
        let paths = i.int("paths")?;
        if paths < 2 {
            return fail("E_INPUT", "paths must be at least 2");
        }
        let seed = i.seed()?;
        let o = GbmOption {
            spot: i.f64("spot")?,
            strike: i.f64("strike")?,
            expiry_years: i.f64("expiry_years")?,
            rate: i.f64("rate")?,
            dividend_yield: i.f64("dividend_yield")?,
            vol: i.f64("vol")?,
        };
        let eps = i.opt_f64("smoothing_width")?;
        let h = i.opt_f64("bump_relative")?;
        i.gate()?;
        let m = match (method, eps, h) {
            ("PATHWISE", e, None) => Method::Pathwise(e),
            ("LIKELIHOOD_RATIO", None, None) => Method::LikelihoodRatio,
            ("BUMP", None, Some(h)) => Method::Bump(h),
            ("BUMP", None, None) => return fail("E_INPUT", "BUMP needs bump_relative"),
            _ => return fail("E_INPUT", "smoothing_width or bump_relative does not fit the method"),
        };
        let paths = u64::try_from(paths).unwrap_or(0);
        let g = mc_greeks(&o, payoff, m, paths, seed)?;
        plain(obj([
            ("price", g.price.into()),
            ("price_se", g.price_se.into()),
            ("delta", g.delta.into()),
            ("delta_se", g.delta_se.into()),
            ("vega", g.vega.into()),
            ("vega_se", g.vega_se.into()),
        ]))
    },
    "risk.model_reserve.dispersion" => {
        let mut prices = Vec::new();
        match i.req("prices")? {
            quantforge_core::json::Json::Obj(m) => {
                for (k, v) in m {
                    let Some(x) = v.as_f64() else {
                        return i.fail("prices", "expected numbers");
                    };
                    prices.push((k.clone(), x));
                }
            }
            _ => return i.fail("prices", "expected an object"),
        }
        let r = i.str("reference_model")?;
        i.gate()?;
        let o = quantforge_core::xva::model_reserve(&prices, r)?;
        plain(obj([
            ("mean", o.mean.into()),
            ("range", o.range.into()),
            ("half_range", o.half_range.into()),
            ("reserve", o.reserve.into()),
            ("worst_model", o.worst_model.as_str().into()),
            ("relative_reserve", o.relative_reserve.map_or(quantforge_core::json::Json::Null, Into::into)),
        ]))
    }
}
