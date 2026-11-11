//! `rates.shortrate.*` operations (stage G wave 1, partial: `zcb`).
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::Result;
use quantforge_core::error::fail;
use quantforge_core::json::obj;
use quantforge_core::shortrate::{self as sr, HwCurve, Model, zcb, zcb_option};

/// The model inputs shared by the stage G short-rate operations.
pub(crate) struct ModelIn {
    name: String,
    a: f64,
    sigma: f64,
    b: Option<f64>,
    curve: Option<(Vec<f64>, Vec<f64>)>,
    /// `short_rate` (`r(0)`), 0 for Hull-White, which refuses it (G-5).
    pub r0: f64,
    hw: Option<HwCurve>,
}

impl ModelIn {
    /// Reads `model` (absent: `default`), its parameters and the `short_rate` rule.
    pub(crate) fn read(i: &Inputs, default: Option<&str>) -> Result<ModelIn> {
        let name = match (i.opt("model"), default) {
            (None, Some(d)) => d.to_string(),
            _ => i.str("model")?.to_string(),
        };
        if !matches!(name.as_str(), "VASICEK" | "CIR" | "HULL_WHITE") {
            return fail("E_INPUT", "model must be VASICEK, CIR or HULL_WHITE");
        }
        let hw = name == "HULL_WHITE";
        let (a, sigma) = (i.f64("mean_reversion")?, i.f64("sigma")?);
        let r0 = if hw {
            if i.opt("short_rate").is_some() {
                return fail("E_INPUT", "HULL_WHITE takes no short_rate");
            }
            0.0
        } else {
            i.f64("short_rate")?
        };
        let curve = if hw {
            let c = super::rates::sub(i, "curve")?;
            Some((c.reals("times")?, c.reals("discount_factors")?))
        } else {
            None
        };
        let b = if hw {
            None
        } else {
            Some(i.f64("long_term_mean")?)
        };
        Ok(ModelIn {
            name,
            a,
            sigma,
            b,
            curve,
            r0,
            hw: None,
        })
    }

    /// Validates the curve (after `gate`) so that [`ModelIn::model`] can borrow it.
    pub(crate) fn build(&mut self) -> Result<()> {
        if let Some((t, d)) = &self.curve {
            if t.len() > 10_000 {
                return fail("E_LIMIT", "at most 10,000 curve pillars");
            }
            self.hw = Some(HwCurve::new(t, d)?);
        }
        Ok(())
    }

    pub(crate) fn model(&self) -> Model<'_> {
        let (a, sigma) = (self.a, self.sigma);
        match (self.name.as_str(), self.b, &self.hw) {
            ("VASICEK", Some(b), _) => Model::Vasicek { a, b, sigma },
            ("CIR", Some(b), _) => Model::Cir { a, b, sigma },
            (_, _, Some(curve)) => Model::HullWhite { a, sigma, curve },
            _ => unreachable!("ModelIn::build runs first"),
        }
    }
}

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
    },
    "rates.shortrate.zcb_option" => {
        let model = i.str("model")?;
        let (a, sigma) = (i.f64("mean_reversion")?, i.f64("sigma")?);
        let hw_model = model == "HULL_WHITE";
        let r = if hw_model {
            if i.opt("short_rate").is_some() {
                return fail("E_INPUT", "HULL_WHITE takes no short_rate");
            }
            0.0
        } else {
            i.f64("short_rate")?
        };
        let curve = if hw_model {
            let c = super::rates::sub(i, "curve")?;
            Some((c.reals("times")?, c.reals("discount_factors")?))
        } else {
            None
        };
        let b = match model {
            "VASICEK" | "CIR" => Some(i.f64("long_term_mean")?),
            _ => None,
        };
        let call = match i.str("option_type")? {
            "CALL" => true,
            "PUT" => false,
            _ => return fail("E_INPUT", "option_type must be CALL or PUT"),
        };
        let (k, te, ts) = (i.f64("strike")?, i.f64("expiry_years")?, i.f64("maturity_years")?);
        let notional = i.f64("notional")?;
        i.gate()?;
        let hw;
        let m = match (model, b, curve) {
            ("VASICEK", Some(b), _) => Model::Vasicek { a, b, sigma },
            ("CIR", Some(b), _) => Model::Cir { a, b, sigma },
            ("HULL_WHITE", _, Some((t, d))) => {
                hw = HwCurve::new(&t, &d)?;
                Model::HullWhite { a, sigma, curve: &hw }
            }
            _ => return fail("E_INPUT", "model must be VASICEK, CIR or HULL_WHITE"),
        };
        let (price, pt, ps) = zcb_option(&m, r, call, k, te, ts, notional)?;
        plain(obj([
            ("price", price.into()),
            ("bond_price_expiry", pt.into()),
            ("bond_price_maturity", ps.into()),
        ]))
    },
    "rates.shortrate.swaption" => {
        let mut mi = ModelIn::read(i, Some("HULL_WHITE"))?;
        let te = i.f64("expiry_years")?;
        let pay = i.reals("payment_times")?;
        let k = i.f64("fixed_rate")?;
        let st = i.str("swaption_type")?;
        let notional = i.f64("notional")?;
        i.gate()?;
        mi.build()?;
        let m = mi.model();
        sr::discount0(&m, mi.r0, 1.0)?;
        if te <= 0.0 {
            return fail("E_DOMAIN", "expiry_years must be positive");
        }
        sr::check_payments(te, &pay)?;
        let payer = match st {
            "PAYER" => true,
            "RECEIVER" => false,
            _ => return fail("E_INPUT", "swaption_type must be PAYER or RECEIVER"),
        };
        let v = sr::swaption(&m, mi.r0, te, &pay, k, payer, notional)?;
        plain(obj([
            ("price", v.price.into()),
            ("forward_swap_rate", v.forward_swap_rate.into()),
            ("annuity", v.annuity.into()),
        ]))
    },
    "rates.shortrate.capfloor" => {
        let mut mi = ModelIn::read(i, None)?;
        let times = i.reals("period_times")?;
        let k = i.f64("strike")?;
        let cf = i.str("cap_floor")?;
        let notional = i.f64("notional")?;
        i.gate()?;
        mi.build()?;
        let cap = match cf {
            "CAP" => true,
            "FLOOR" => false,
            _ => return fail("E_INPUT", "cap_floor must be CAP or FLOOR"),
        };
        let (p, lets) = sr::capfloor(&mi.model(), mi.r0, &times, k, cap, notional)?;
        plain(obj([("price", p.into()), ("caplet_prices", lets.into())]))
    },
    "rates.g2pp.zcb" | "rates.g2pp.zcb_option" => {
        let g = |k: &str| i.f64(k);
        let (a, sigma, b, eta, rho) = (g("a")?, g("sigma")?, g("b")?, g("eta")?, g("rho")?);
        let c = super::rates::sub(i, "curve")?;
        let (ts, ds) = (c.reals("times")?, c.reals("discount_factors")?);
        if op == "rates.g2pp.zcb" {
            let (x, y, t, mat) = (g("x")?, g("y")?, g("t_years")?, g("maturity_years")?);
            i.gate()?;
            let curve = HwCurve::new(&ts, &ds)?;
            let m = sr::G2pp { a, sigma, b, eta, rho, curve: &curve };
            let (p, z) = m.zcb(x, y, t, mat)?;
            return plain(obj([("discount_factor", p.into()), ("zero_rate", z.into())]));
        }
        if i.opt("x").is_some() || i.opt("y").is_some() {
            return fail("E_INPUT", "the option takes no factor states");
        }
        let call = match i.str("option_type")? {
            "CALL" => true,
            "PUT" => false,
            _ => return fail("E_INPUT", "option_type must be CALL or PUT"),
        };
        let (k, te, tm, n) = (g("strike")?, g("expiry_years")?, g("maturity_years")?, g("notional")?);
        i.gate()?;
        let curve = HwCurve::new(&ts, &ds)?;
        let m = sr::G2pp { a, sigma, b, eta, rho, curve: &curve };
        let (p, pt, ps) = m.zcb_option(call, k, te, tm, n)?;
        plain(obj([
            ("price", p.into()),
            ("bond_price_expiry", pt.into()),
            ("bond_price_maturity", ps.into()),
        ]))
    },
    "rates.shortrate.hw_calibrate" => {
        let a = i.f64("mean_reversion")?;
        let c = super::rates::sub(i, "curve")?;
        let (ts, ds) = (c.reals("times")?, c.reals("discount_factors")?);
        let mut strip = Vec::new();
        for (j, v) in i.array("swaptions")?.iter().enumerate() {
            if !matches!(v, quantforge_core::json::Json::Obj(_)) {
                return i.fail("swaptions", "entries must be objects");
            }
            let q = Inputs::new(v);
            let payer = match q.str("swaption_type")? {
                "PAYER" => true,
                "RECEIVER" => false,
                _ => return fail("E_INPUT", format!("swaptions[{j}].swaption_type must be PAYER or RECEIVER")),
            };
            strip.push(sr::CalibSwaption {
                expiry: q.f64("expiry_years")?,
                pay: q.reals("payment_times")?,
                fixed_rate: q.f64("fixed_rate")?,
                payer,
                target: q.f64("target_price")?,
            });
        }
        i.gate()?;
        if ts.len() > 10_000 {
            return fail("E_LIMIT", "at most 10,000 curve pillars");
        }
        let curve = HwCurve::new(&ts, &ds)?;
        let (sigma, px, rmse) = sr::hw_calibrate(&curve, a, &strip)?;
        plain(obj([
            ("sigma", sigma.into()),
            ("fitted_prices", px.into()),
            ("rmse", rmse.into()),
        ]))
    }
}
