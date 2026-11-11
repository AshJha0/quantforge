//! `xva.*` operations (stage G wave 4a: closed-form swap exposure under Hull-White).
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::{Result, fail};
use quantforge_core::json::{Json, obj};
use quantforge_core::shortrate::{self as sr, HwCurve};
use quantforge_core::xva;

super::registry! {
(op, i)
    "xva.exposure.swap_ee_hw" => {
        let (a, sigma) = (i.f64("mean_reversion")?, i.f64("sigma")?);
        if i.opt("short_rate").is_some() {
            return fail("E_INPUT", "HULL_WHITE takes no short_rate");
        }
        let c = super::rates::sub(i, "curve")?;
        let (ts, ds) = (c.reals("times")?, c.reals("discount_factors")?);
        let start = i.f64("start_years")?;
        let pay = i.reals("payment_times")?;
        let k = i.f64("fixed_rate")?;
        let side = i.str("side")?;
        let notional = i.f64("notional")?;
        let ex = i.reals("exposure_times")?;
        let credit = (i.opt_f64("hazard_rate")?, i.opt_f64("recovery")?);
        i.gate()?;
        if ts.len() > 10_000 {
            return fail("E_LIMIT", "at most 10,000 curve pillars");
        }
        let curve = HwCurve::new(&ts, &ds)?;
        let payer = match side {
            "PAY" => true,
            "RECEIVE" => false,
            _ => return fail("E_INPUT", "side must be PAY or RECEIVE"),
        };
        let swap = sr::SwapLeg { start, pay: &pay, fixed_rate: k, payer, notional };
        let (ee, cva) = sr::swap_ee_hw(&curve, a, sigma, &swap, &ex, credit)?;
        plain(match cva {
            Some(c) => obj([("discounted_ee", Json::from(ee)), ("cva", c.into())]),
            None => obj([("discounted_ee", Json::from(ee))]),
        })
    },
    "xva.exposure.collateralised" => {
        let times = i.reals("times")?;
        let q = i.f64("pfe_quantile")?;
        let mut sets: Vec<(String, Vec<Vec<f64>>)> = Vec::new();
        for t in i.array("trades")? {
            if !matches!(t, Json::Obj(_)) {
                return i.fail("trades", "entries must be objects");
            }
            let ti = Inputs::new(t);
            let name = ti.str("netting_set")?.to_string();
            let vals = ti.matrix("values")?;
            match sets.iter_mut().find(|s| s.0 == name) {
                Some(s) => {
                    if s.1.len() != vals.len() {
                        return fail("E_INPUT", "trades of one set need the same number of paths");
                    }
                    for (acc, v) in s.1.iter_mut().zip(&vals) {
                        if acc.len() != v.len() {
                            return fail("E_INPUT", "every path needs the length of times");
                        }
                        for (a, b) in acc.iter_mut().zip(v) {
                            *a += b;
                        }
                    }
                }
                None => sets.push((name, vals)),
            }
        }
        let mut csas: Vec<(String, xva::Csa)> = Vec::new();
        if let Some(Json::Obj(m)) = i.opt("csa") {
            for (name, v) in m {
                let c = Inputs::new(v);
                csas.push((name.clone(), xva::Csa {
                    threshold_receive: c.f64("threshold_receive")?,
                    threshold_post: c.f64("threshold_post")?,
                    mta: c.f64("minimum_transfer_amount")?,
                    mpor_steps: c.int("mpor_steps")?,
                    independent_amount: c.f64_or("independent_amount", 0.0)?,
                }));
            }
        } else if i.opt("csa").is_some() {
            return i.fail("csa", "expected an object");
        }
        i.gate()?;
        if sets.is_empty() {
            return fail("E_INPUT", "trades needs at least one trade");
        }
        let refs: Vec<&xva::Csa> = csas.iter().map(|c| &c.1).collect();
        xva::check_collateral_inputs(&times, q, &refs)?;
        if sets.iter().any(|s| s.1.is_empty() || s.1.iter().any(|p| p.len() != times.len())) {
            return fail("E_INPUT", "every path needs the length of times");
        }
        if csas.iter().any(|c| !sets.iter().any(|s| s.0 == c.0)) {
            return fail("E_INPUT", "csa names a netting set with no trades");
        }
        for s in &sets {
            for p in &s.1 {
                quantforge_core::error::finite("values", &p.as_slice())?;
            }
        }
        sets.sort_by(|a, b| a.0.cmp(&b.0));
        let mut total = vec![0.0; times.len()];
        let mut out = Vec::new();
        for (name, paths) in &sets {
            let c = csas.iter().find(|c| &c.0 == name).map(|c| &c.1);
            let r = xva::set_exposure(&times, paths, c, q)?;
            for (t, e) in total.iter_mut().zip(&r.ee) {
                *t += e;
            }
            out.push((name.clone(), obj([
                ("ee", r.ee.into()),
                ("ene", r.ene.into()),
                ("pfe", r.pfe.into()),
                ("epe", r.epe.into()),
                ("effective_epe", r.effective_epe.into()),
            ])));
        }
        plain(obj([("netting_sets", Json::Obj(out)), ("total_ee", total.into())]))
    },
    "xva.adjustments.value" => {
        let name = |k: &str| -> Result<xva::Name> {
            let c = super::rates::sub(i, k)?;
            Ok(xva::Name { hazard_rate: c.f64("hazard_rate")?, recovery: c.f64("recovery")? })
        };
        let f = super::rates::sub(i, "funding")?;
        let pair = |a: &str, b: &str| -> Result<Option<(Vec<f64>, f64)>> {
            match (i.opt(a).is_some(), i.opt(b).is_some()) {
                (true, true) => Ok(Some((i.reals(a)?, i.f64(b)?))),
                (false, false) => Ok(None),
                _ => fail("E_INPUT", format!("{a} and {b} go together")),
            }
        };
        let x = xva::AdjInputs {
            times: i.reals("times")?,
            discount_factors: i.reals("discount_factors")?,
            ee: i.reals("ee")?,
            ene: i.reals("ene")?,
            counterparty: name("counterparty")?,
            own: name("own")?,
            borrow_spread: f.f64("borrow_spread")?,
            lend_spread: f.f64("lend_spread")?,
            exclude_dva_overlap: f.bool("exclude_dva_overlap")?,
            im: pair("im", "im_spread")?,
            capital: pair("capital", "hurdle_rate")?,
        };
        i.gate()?;
        let r = xva::adjustments(&x)?;
        let mut o = vec![
            ("cva".to_string(), Json::from(r.cva)),
            ("dva".to_string(), r.dva.into()),
            ("fca".to_string(), r.fca.into()),
            ("fba".to_string(), r.fba.into()),
            ("fva".to_string(), r.fva.into()),
        ];
        if let Some(m) = r.mva {
            o.push(("mva".to_string(), m.into()));
        }
        if let Some(k) = r.kva {
            o.push(("kva".to_string(), k.into()));
        }
        plain(Json::Obj(o))
    },
    "xva.simm.ir_delta" => {
        let s = i.reals("sensitivities")?;
        let rw = i.reals("risk_weights")?;
        let rho = i.matrix("correlations")?;
        let t = i.f64("concentration_threshold")?;
        i.gate()?;
        let (ws, cr, m) = xva::simm_ir_delta(&s, &rw, &rho, t)?;
        plain(obj([
            ("weighted_sensitivities", ws.into()),
            ("concentration_factor", cr.into()),
            ("margin", m.into()),
        ]))
    },
    "xva.wwr.cva_hw" => {
        let t = i.reals("times")?;
        let v = i.matrix("values")?;
        let d = i.reals("discount_factors")?;
        let h = i.f64("hazard_rate")?;
        let r = i.f64("recovery")?;
        let b = i.f64("wwr_b")?;
        i.gate()?;
        let (cva, a) = xva::wwr_cva_hw(&t, &v, &d, h, r, b)?;
        plain(obj([("cva", cva.into()), ("a", a.into())]))
    }
}
