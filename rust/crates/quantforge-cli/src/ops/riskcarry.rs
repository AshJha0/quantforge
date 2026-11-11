//! Stage F carry-over operations landed in stage G: F3 sensitivities, F4 portfolio-risk tools,
//! FRTB FX, equity, CSR and commodity delta.
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::{Result, fail};
use quantforge_core::frtb::GirrDelta;
use quantforge_core::frtb2 as f2;
use quantforge_core::frtb3 as f3;
use quantforge_core::json::{Json, obj};
use quantforge_core::risk_carry as rc;

fn sbm_out(r: &GirrDelta) -> Result<Outcome> {
    sbm_named(r, "delta")
}

fn sbm_named(r: &GirrDelta, measure: &str) -> Result<Outcome> {
    let scen: Vec<(String, Json)> = r
        .scenarios
        .iter()
        .map(|s| {
            let b: Vec<Json> = s
                .buckets
                .iter()
                .map(|b| {
                    obj([
                        ("bucket", b.currency.as_str().into()),
                        ("k", b.k.into()),
                        ("s", b.s.into()),
                        ("s_used", b.s_used.into()),
                    ])
                })
                .collect();
            (
                s.name.to_string(),
                obj([
                    ("buckets", Json::Arr(b)),
                    (measure, s.delta.into()),
                    ("alternative_used", Json::Bool(s.alternative_used)),
                ]),
            )
        })
        .collect();
    plain(obj([
        ("scenarios", Json::Obj(scen)),
        ("capital", r.capital.into()),
        ("binding_scenario", r.binding_scenario.into()),
    ]))
}

fn rows<'a>(i: &Inputs<'a>, k: &str) -> Result<Vec<Inputs<'a>>> {
    i.array(k)?
        .iter()
        .map(|v| {
            if matches!(v, Json::Obj(_)) {
                Ok(Inputs::new(v))
            } else {
                i.fail(k, "entries must be objects")
            }
        })
        .collect()
}

fn named<'a>(i: &Inputs<'a>, k: &str) -> Result<Vec<(String, &'a Json)>> {
    match i.req(k)? {
        Json::Obj(m) => Ok(m.iter().map(|(n, v)| (n.clone(), v)).collect()),
        _ => i.fail(k, "expected an object"),
    }
}

/// A bucket label given as a string or an integer.
fn label(r: &Inputs) -> Result<String> {
    match r.req("bucket")? {
        Json::Str(s) => Ok(s.clone()),
        Json::Int(n) => Ok(n.to_string()),
        _ => r.fail("bucket", "expected a string or an integer"),
    }
}

fn class(i: &Inputs) -> Result<f3::Class> {
    match f3::Class::parse(i.str("risk_class")?) {
        Some(c) => Ok(c),
        None => fail(
            "E_INPUT",
            "risk_class must be GIRR, CSR_NONSEC, EQUITY, COMMODITY or FX",
        ),
    }
}

fn opt_name(r: &Inputs) -> Result<Option<String>> {
    r.opt("name")
        .map(|_| r.str("name").map(str::to_string))
        .transpose()
}

super::registry! {
(op, i)
    "risk.sens.inflation01" => {
        let (n, y) = (i.f64("notional")?, i.int("years")?);
        let (k, z, p) = (i.f64("fixed_rate")?, i.f64("market_rate")?, i.f64("discount_factor")?);
        i.gate()?;
        let (pv, a, b) = rc::inflation01(n, y, k, z, p)?;
        plain(obj([("pv", pv.into()), ("inflation01", a.into()), ("inflation01_bump", b.into())]))
    },
    "risk.sens.dividend_borrow" => {
        let g = |k: &str| i.f64(k);
        let (s, k, t, r) = (g("spot")?, g("strike")?, g("expiry_years")?, g("rate")?);
        let (q, b, v) = (g("dividend_yield")?, g("borrow_rate")?, g("vol")?);
        let call = match i.str("option_type")? {
            "CALL" => true,
            "PUT" => false,
            _ => return fail("E_INPUT", "option_type must be CALL or PUT"),
        };
        i.gate()?;
        let (p, d, bo) = rc::dividend_borrow(s, k, t, r, q, b, v, call)?;
        plain(obj([("price", p.into()), ("dividend01", d.into()), ("borrow01", bo.into())]))
    },
    "risk.sens.correlation" => {
        let g = |k: &str| i.f64(k);
        let x = [
            g("spot1")?, g("spot2")?, g("quantity1")?, g("quantity2")?, g("yield1")?,
            g("yield2")?, g("vol1")?, g("vol2")?, g("correlation")?, g("expiry_years")?,
        ];
        i.gate()?;
        let (p, c, sv) = rc::correlation01(x[0], x[1], x[2], x[3], x[4], x[5], x[6], x[7], x[8], x[9])?;
        plain(obj([("price", p.into()), ("correlation01", c.into()), ("spread_vol", sv.into())]))
    },
    "risk.stress.reverse" => {
        let d = i.reals("direction")?;
        let de = i.reals("delta")?;
        let g = i.matrix("gamma")?;
        let l = i.f64("target_loss")?;
        i.gate()?;
        let (k, sh, pnl) = rc::reverse_stress(&d, &de, &g, l)?;
        plain(obj([("scale", k.into()), ("shocks", sh.into()), ("pnl", pnl.into())]))
    },
    "risk.limits.check" => {
        let measures = named(i, "measures")?;
        let limits = named(i, "limits")?;
        let mut vals = Vec::new();
        for (n, v) in &measures {
            let Some(x) = v.as_f64() else { return i.fail("measures", "expected numbers") };
            vals.push((n.clone(), x));
        }
        let mut lims = Vec::new();
        for (n, v) in &limits {
            if !matches!(v, Json::Obj(_)) {
                return i.fail("limits", "entries must be objects");
            }
            let l = Inputs::new(v);
            lims.push((n.clone(), l.f64("soft")?, l.f64("hard")?));
        }
        i.gate()?;
        vals.sort_by(|a, b| a.0.cmp(&b.0));
        let mut out = Vec::new();
        let mut worst = 0;
        for (n, x) in &vals {
            let Some(l) = lims.iter().find(|l| &l.0 == n) else {
                return fail("E_INPUT", format!("measure {n} has no limit"));
            };
            let (u, st) = rc::limit_status(*x, l.1, l.2)?;
            let rank = match st { "BREACH" => 2, "WARN" => 1, _ => 0 };
            worst = worst.max(rank);
            out.push((n.clone(), obj([("utilisation", u.into()), ("status", st.into())])));
        }
        for l in &lims {
            rc::limit_status(0.0, l.1, l.2)?;
        }
        let overall = ["OK", "WARN", "BREACH"][worst];
        plain(obj([("measures", Json::Obj(out)), ("overall", overall.into())]))
    },
    "risk.concentration.measures" => {
        let x = i.reals("exposures")?;
        let n = i.int("top_n")?;
        i.gate()?;
        let (h, e, t, w) = rc::concentration(&x, n)?;
        plain(obj([
            ("hhi", h.into()),
            ("effective_number", e.into()),
            ("top_n_share", t.into()),
            ("weights", w.into()),
        ]))
    },
    "risk.var.liquidity_adjusted" => {
        let (v, z) = (i.f64("var")?, i.f64("z")?);
        let p = i.reals("position_values")?;
        let m = i.reals("spread_mean")?;
        let s = i.reals("spread_vol")?;
        i.gate()?;
        let (c, l) = rc::liquidity_adjusted(v, z, &p, &m, &s)?;
        plain(obj([("liquidity_cost", c.into()), ("lvar", l.into())]))
    },
    "risk.vol.horizon" => {
        let (s, r, h) = (i.f64("daily_vol")?, i.f64("ar1")?, i.int("horizon_days")?);
        i.gate()?;
        let (v, sq, ratio) = rc::vol_horizon(s, r, h)?;
        plain(obj([("vol", v.into()), ("sqrt_rule_vol", sq.into()), ("variance_ratio", ratio.into())]))
    },
    "risk.frtb.fx_delta" => {
        let mut sens = Vec::new();
        for r in rows(i, "sensitivities")? {
            sens.push((r.str("pair")?.to_string(), r.f64("sensitivity")?));
        }
        let spec: Vec<String> = match i.opt("specified_pairs") {
            None => Vec::new(),
            Some(_) => i.array("specified_pairs")?
                .iter()
                .map(|v| v.as_str().map(str::to_string).ok_or(()))
                .collect::<std::result::Result<_, _>>()
                .or_else(|()| i.fail("specified_pairs", "expected strings"))?,
        };
        i.gate()?;
        sbm_out(&f2::fx_delta(&sens, &spec)?)
    },
    "risk.frtb.equity_delta" => {
        let mut sens = Vec::new();
        for r in rows(i, "sensitivities")? {
            sens.push(f2::EquitySens {
                issuer: r.str("issuer")?.to_string(),
                bucket: r.int("bucket")?,
                kind: r.str("kind")?.to_string(),
                sensitivity: r.f64("sensitivity")?,
            });
        }
        i.gate()?;
        sbm_out(&f2::equity_delta(&sens)?)
    },
    "risk.frtb.csr_delta" => {
        let mut sens = Vec::new();
        for r in rows(i, "sensitivities")? {
            sens.push(f2::CsrSens {
                issuer: r.str("issuer")?.to_string(),
                bucket: r.int("bucket")?,
                tenor: r.str("tenor")?.to_string(),
                curve: r.str("curve")?.to_string(),
                sensitivity: r.f64("sensitivity")?,
            });
        }
        i.gate()?;
        sbm_out(&f2::csr_delta(&sens)?)
    },
    "risk.frtb.commodity_delta" => {
        let mut sens = Vec::new();
        for r in rows(i, "sensitivities")? {
            sens.push(f2::CommoditySens {
                commodity: r.str("commodity")?.to_string(),
                bucket: r.int("bucket")?,
                tenor: r.str("tenor")?.to_string(),
                location: r.str("location")?.to_string(),
                sensitivity: r.f64("sensitivity")?,
            });
        }
        i.gate()?;
        sbm_out(&f2::commodity_delta(&sens)?)
    },
    "risk.frtb.vega" => {
        let c = class(i)?;
        let mut sens = Vec::new();
        for r in rows(i, "sensitivities")? {
            sens.push(f3::VegaSens {
                bucket: label(&r)?,
                name: opt_name(&r)?,
                option_maturity: r.f64("option_maturity")?,
                underlying_maturity: r.opt_f64("underlying_maturity")?,
                vega: r.f64("vega")?,
            });
        }
        i.gate()?;
        sbm_named(&f3::vega(c, &sens)?, "vega")
    },
    "risk.frtb.curvature" => {
        let c = class(i)?;
        let mut fs = Vec::new();
        for r in rows(i, "factors")? {
            fs.push(f3::CurvFactor {
                bucket: label(&r)?,
                name: opt_name(&r)?,
                cvr_up: r.f64("cvr_up")?,
                cvr_down: r.f64("cvr_down")?,
            });
        }
        let fx = i.bool_or("fx_scalar", false)?;
        if i.opt("fx_scalar").is_some() && c != f3::Class::Fx {
            return fail("E_INPUT", "fx_scalar applies to FX only");
        }
        i.gate()?;
        let r = f3::curvature(c, &fs, fx)?;
        let scen: Vec<(String, Json)> = r
            .scenarios
            .iter()
            .map(|(n, b, k)| {
                let bs: Vec<Json> = b
                    .iter()
                    .map(|x| {
                        obj([
                            ("bucket", x.bucket.as_str().into()),
                            ("k", x.k.into()),
                            ("s", x.s.into()),
                            ("selected", if x.up { "UP" } else { "DOWN" }.into()),
                        ])
                    })
                    .collect();
                ((*n).to_string(), obj([("buckets", Json::Arr(bs)), ("curvature", (*k).into())]))
            })
            .collect();
        plain(obj([
            ("scenarios", Json::Obj(scen)),
            ("capital", r.capital.into()),
            ("binding_scenario", r.binding_scenario.into()),
        ]))
    }
}
