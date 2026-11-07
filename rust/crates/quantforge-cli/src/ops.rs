//! One arm per operation: read the inputs, call the library, shape the outputs.
use crate::functions::{Fun, plain_function, root_function};
use crate::input::{Inputs, parse_u64};
use quantforge_core::calendar::parse_tenor;
use quantforge_core::compounding::{self, Compounding};
use quantforge_core::cos::{self, CosInputs, Model};
use quantforge_core::data::{CheckInputs, Quote, check_quotes};
use quantforge_core::daycount::{DayCountInputs, year_fraction};
use quantforge_core::error::{Result, fail};
use quantforge_core::interp::{self, Method};
use quantforge_core::json::{Json, obj};
use quantforge_core::mc::{self, McInputs};
use quantforge_core::pde::{self, PdeInputs};
use quantforge_core::rng::{Xoshiro, inverse_normal, ppnd16};
use quantforge_core::root::{self, Controls, Root};
use quantforge_core::store::{Log, check_range};
use quantforge_core::time::parse_instant;
use quantforge_core::{integrate, linalg, snapshot, sobol, stats, time, ts};
use std::collections::HashMap;

pub struct Outcome {
    pub outputs: Json,
    pub diagnostics: Json,
}

pub fn plain(outputs: Json) -> Result<Outcome> {
    Ok(Outcome {
        outputs,
        diagnostics: Json::Obj(Vec::new()),
    })
}

/// Sorted. A test checks the order and that each name dispatches.
pub const OPERATIONS: &[&str] = &[
    "bond.fit.nelson_siegel",
    "bond.frn.price",
    "bond.futures.basis",
    "bond.futures.conversion_factor",
    "bond.price.from_curve",
    "bond.price.from_yield",
    "bond.spread.asset_swap",
    "bond.spread.z",
    "bond.yield.from_price",
    "calib.check_bid_ask",
    "calib.curve.robust",
    "calib.curve.smooth",
    "calib.curve_report",
    "calib.fit",
    "core.calendar.add_business_days",
    "core.calendar.add_tenor",
    "core.calendar.adjust",
    "core.calendar.business_days_between",
    "core.calendar.holidays",
    "core.calendar.is_business_day",
    "core.compounding.convert",
    "core.compounding.discount_factor",
    "core.conventions.lookup",
    "core.cos.european",
    "core.data.check_quotes",
    "core.daycount.year_fraction",
    "core.diff.central",
    "core.integrate.adaptive_simpson",
    "core.integrate.gauss_kronrod",
    "core.integrate.gauss_legendre",
    "core.integrate.simpson",
    "core.integrate.trapezoid",
    "core.interp.evaluate",
    "core.interp.monotone_convex",
    "core.linalg.cholesky",
    "core.linalg.eigen_symmetric",
    "core.linalg.solve",
    "core.mc.gbm_european",
    "core.pde.bs_european",
    "core.rng.inverse_normal",
    "core.rng.next_u64",
    "core.rng.normals",
    "core.rng.set_state_next_u64",
    "core.rng.uniforms",
    "core.root.bisection",
    "core.root.brent",
    "core.root.newton",
    "core.snapshot.hash",
    "core.sobol.points",
    "core.stats.covariance",
    "core.stats.normal",
    "core.stats.ols",
    "core.stats.quantile",
    "core.stats.summary",
    "core.store.chain",
    "core.store.latest",
    "core.store.query_as_of",
    "core.store.replay",
    "core.store.snapshot",
    "core.time.business_date",
    "core.time.to_instant",
    "core.time.to_local",
    "core.time.utc_offset",
    "core.ts.ar1",
    "core.ts.autocorrelation",
    "core.ts.ewma_variance",
    "core.ts.forward_fill",
    "core.ts.ljung_box",
    "core.ts.resample_last",
    "core.ts.returns",
    "core.ts.rolling",
    "core.units.add_money",
    "core.units.convert",
    "core.units.round_money",
    "eq.forward.flat",
    "eq.forward.outright",
    "eq.forward.parity",
    "fx.curve.implied",
    "fx.forward.outright",
    "fx.forward.pv",
    "fx.ndf.pv",
    "fx.spot_date",
    "fx.swap.pv",
    "fx.xccy.bootstrap",
    "fx.xccy.pv",
    "hedge.solve",
    "hedge.spread_cost",
    "rates.basis.ois_spread",
    "rates.basis.spread",
    "rates.csa.discount",
    "rates.curve.discount",
    "rates.curve.forward",
    "rates.curve.joint_bootstrap",
    "rates.fallback.rate",
    "rates.fra.pv",
    "rates.futures.convexity",
    "rates.ois.bootstrap",
    "rates.ois.compound",
    "rates.ois.compound_dated",
    "rates.ois.fit_steps",
    "rates.ois.pv",
    "rates.ois.step_curve",
    "rates.projection.bootstrap",
    "rates.schedule.generate",
    "rates.swap.pv",
    "repo.forward",
    "repo.implied_rate",
    "risk.cashflows",
    "risk.ois.dv01",
    "risk.vol.bump_greeks",
    "risk.vol.greeks",
    "risk.vol.surface_vega",
    "usecase.fx_hedge",
    "usecase.rates_hedge",
    "usecase.vol_surface",
    "vol.delta.from_strike",
    "vol.delta.to_strike",
    "vol.equity.price",
    "vol.option.implied",
    "vol.option.price",
    "vol.sabr.arbfree",
    "vol.sabr.calibrate",
    "vol.sabr.density",
    "vol.sabr.hagan",
    "vol.smile.rr_bf",
    "vol.ssvi.calibrate",
    "vol.ssvi.evaluate",
    "vol.surface.check",
    "vol.surface.query",
    "vol.svi.calibrate",
    "vol.svi.evaluate",
];

pub fn dispatch(op: &str, i: &Inputs) -> Result<Outcome> {
    match op {
        "core.calendar.add_business_days" => {
            let (c, d, n) = (i.calendar("calendar")?, i.date("date")?, i.int("days")?);
            i.gate()?;
            plain(obj([(
                "date",
                c.add_business_days(d, n)?.to_string().into(),
            )]))
        }
        "core.calendar.add_tenor" => add_tenor(i),
        "core.calendar.adjust" => {
            let (c, d) = (i.calendar("calendar")?, i.date("date")?);
            let b = i.bdc("convention")?;
            plain(obj([("date", c.adjust(d, b)?.to_string().into())]))
        }
        "core.calendar.business_days_between" => {
            let (c, s, e) = (i.calendar("calendar")?, i.date("start")?, i.date("end")?);
            plain(obj([("count", c.business_days_between(s, e)?.into())]))
        }
        "core.calendar.holidays" => {
            let (c, y) = (i.calendar("calendar")?, i.int("year")?);
            let y = i32::try_from(y).unwrap_or(i32::MAX);
            let list: Vec<String> = c.holidays(y)?.iter().map(ToString::to_string).collect();
            plain(obj([("dates", list.into())]))
        }
        "core.calendar.is_business_day" => {
            let (c, d) = (i.calendar("calendar")?, i.date("date")?);
            plain(obj([("is_business_day", c.is_business_day(d)?.into())]))
        }
        "core.compounding.convert" => {
            let (r, t) = (i.f64("rate")?, i.f64("t")?);
            let from = compounding_of(&Inputs::new(i.req("from")?))?;
            let to = compounding_of(&Inputs::new(i.req("to")?))?;
            plain(obj([(
                "rate",
                compounding::convert(r, t, from, to)?.into(),
            )]))
        }
        "core.compounding.discount_factor" => {
            let (r, t, c) = (i.f64("rate")?, i.f64("t")?, compounding_of(i)?);
            let d = compounding::discount_factor(r, t, c)?;
            plain(obj([("discount_factor", d.into())]))
        }
        "core.cos.european" => cos_european(i),
        "core.data.check_quotes" => data_check(i),
        "core.daycount.year_fraction" => {
            let conv = i.str("convention")?;
            let (s, e) = (i.date("start")?, i.date("end")?);
            // Keys a convention does not use are ignored, whatever they hold.
            let icma = conv == "ACT_ACT_ICMA";
            let mut extra = DayCountInputs::default();
            if icma || conv == "ACT_365L" {
                extra.frequency = i.opt_int("frequency")?;
            }
            if icma {
                extra.ref_start = i.opt_date("ref_start")?;
                extra.ref_end = i.opt_date("ref_end")?;
            }
            if conv == "THIRTY_E_360_ISDA" {
                extra.termination = i.opt_date("termination")?;
            }
            if conv == "BUS_252" && i.opt("calendar").is_some() {
                extra.calendar = Some(i.calendar("calendar")?);
            }
            let y = year_fraction(conv, s, e, &extra)?;
            plain(obj([("year_fraction", y.into())]))
        }
        "core.diff.central" => diff(i),
        "core.integrate.adaptive_simpson" => {
            let (f, a, b) = integrand(i)?;
            let (tol, depth) = (i.f64_or("tol", 1e-10)?, i.int_or("max_depth", 50)?);
            i.gate()?;
            let v = integrate::adaptive_simpson(&f, a, b, tol, depth)?;
            plain(obj([("value", v.into())]))
        }
        "core.integrate.gauss_kronrod" => {
            let (f, a, b) = integrand(i)?;
            let (tol, max) = (i.f64_or("tol", 1e-10)?, i.int_or("max_intervals", 500)?);
            i.gate()?;
            let (v, e) = integrate::gauss_kronrod(&f, a, b, tol, max)?;
            Ok(Outcome {
                outputs: obj([("value", v.into())]),
                diagnostics: obj([("error_estimate", e.into())]),
            })
        }
        "core.integrate.gauss_legendre" => fixed_rule(i, integrate::gauss_legendre),
        "core.integrate.simpson" => fixed_rule(i, integrate::simpson),
        "core.integrate.trapezoid" => fixed_rule(i, integrate::trapezoid),
        "core.interp.evaluate" => interp_evaluate(i),
        "core.interp.monotone_convex" => {
            let (t, r, at) = (i.reals("t")?, i.reals("r")?, i.reals("at")?);
            let pos = i.bool_or("positive", false)?;
            i.gate()?;
            let (f, z) = interp::monotone_convex(&t, &r, &at, pos)?;
            plain(obj([("forwards", f.into()), ("zero_rates", z.into())]))
        }
        "core.linalg.cholesky" => {
            let a = i.matrix("a")?;
            i.gate()?;
            plain(obj([("l", linalg::cholesky(&a)?.into())]))
        }
        "core.linalg.eigen_symmetric" => {
            let a = i.matrix("a")?;
            i.gate()?;
            let v = linalg::eigen_symmetric(&a)?;
            plain(obj([("values", v.into())]))
        }
        "core.linalg.solve" => {
            let (a, b) = (i.matrix("a")?, i.reals("b")?);
            i.gate()?;
            plain(obj([("x", linalg::solve(&a, &b)?.into())]))
        }
        "core.mc.gbm_european" => monte_carlo(i),
        "core.pde.bs_european" => pde_european(i),
        "core.rng.inverse_normal" => {
            let p = i.reals("p")?;
            i.gate()?;
            plain(obj([("z", inverse_normal(&p)?.into())]))
        }
        "core.rng.next_u64" => {
            let (mut g, n) = generator(i)?;
            let v: Vec<String> = (0..n).map(|_| g.next_u64().to_string()).collect();
            plain(obj([("values", v.into())]))
        }
        "core.rng.normals" => {
            let (mut g, n) = generator(i)?;
            let v: Vec<f64> = (0..n).map(|_| ppnd16(g.next_uniform())).collect();
            plain(obj([("values", v.into())]))
        }
        "core.rng.uniforms" => {
            let (mut g, n) = generator(i)?;
            let v: Vec<f64> = (0..n).map(|_| g.next_uniform()).collect();
            plain(obj([("values", v.into())]))
        }
        "core.rng.set_state_next_u64" => set_state(i),
        "core.root.bisection" => {
            let (f, _, c) = root_inputs(i)?;
            let (a, b) = (i.f64("a")?, i.f64("b")?);
            i.gate()?;
            root_result(root::bisection(&f, a, b, &c)?)
        }
        "core.root.brent" => {
            let (f, _, c) = root_inputs(i)?;
            let (a, b) = (i.f64("a")?, i.f64("b")?);
            i.gate()?;
            root_result(root::brent(&f, a, b, &c)?)
        }
        "core.root.newton" => {
            let (f, df, c) = root_inputs(i)?;
            let x0 = i.f64("x0")?;
            let bracket = match (i.opt_f64("a")?, i.opt_f64("b")?) {
                (Some(a), Some(b)) => Some((a, b)),
                (None, None) => None,
                _ => return i.fail("a", "a and b must be given together"),
            };
            i.gate()?;
            root_result(root::newton(&f, &df, x0, bracket, &c)?)
        }
        "core.snapshot.hash" => {
            let (canonical, id) = snapshot::hash(i.str("document_text")?)?;
            plain(obj([
                ("canonical", canonical.into()),
                ("snapshot_id", id.into()),
            ]))
        }
        "core.sobol.points" => {
            let (d, n, s) = (i.int("dimensions")?, i.int("count")?, i.int_or("skip", 0)?);
            i.gate()?;
            plain(obj([("points", sobol::points(d, n, s)?.into())]))
        }
        "core.stats.covariance" => {
            let (x, y) = (i.reals("x")?, i.reals("y")?);
            i.gate()?;
            let (c, r) = stats::covariance(&x, &y)?;
            plain(obj([("covariance", c.into()), ("correlation", r.into())]))
        }
        "core.stats.normal" => {
            let x = i.reals("x")?;
            i.gate()?;
            let pdf: Vec<f64> = x.iter().map(|v| stats::normal_pdf(*v)).collect();
            let cdf: Vec<f64> = x.iter().map(|v| stats::normal_cdf(*v)).collect();
            plain(obj([("pdf", pdf.into()), ("cdf", cdf.into())]))
        }
        "core.stats.ols" => {
            let (x, y) = (i.reals("x")?, i.reals("y")?);
            i.gate()?;
            let o = stats::ols(&x, &y)?;
            plain(obj([
                ("alpha", o.alpha.into()),
                ("beta", o.beta.into()),
                ("r_squared", o.r_squared.into()),
                ("se_alpha", o.se_alpha.into()),
                ("se_beta", o.se_beta.into()),
            ]))
        }
        "core.stats.quantile" => {
            let (x, p) = (i.reals("x")?, i.reals("p")?);
            i.gate()?;
            let v = stats::quantile(&x, &p)?;
            plain(obj([("values", v.into())]))
        }
        "core.stats.summary" => {
            let x = i.reals("x")?;
            i.gate()?;
            let s = stats::summary(&x)?;
            plain(obj([
                ("count", s.count.into()),
                ("mean", s.mean.into()),
                ("variance", s.variance.into()),
                ("stdev", s.stdev.into()),
                ("skewness", s.skewness.into()),
                ("excess_kurtosis", s.excess_kurtosis.into()),
                ("min", s.min.into()),
                ("max", s.max.into()),
            ]))
        }
        "core.store.chain" => {
            let log = Log::read(i.array("records")?)?;
            i.gate()?;
            log.check()?;
            let (head, hashes) = log.chain();
            plain(obj([("head", head.into()), ("hashes", hashes.into())]))
        }
        "core.store.latest" => {
            let log = Log::read(i.array("records")?)?;
            let (t, s) = (i.instant("as_of")?, i.str("series_id")?);
            i.gate()?;
            log.check()?;
            check_range([t])?;
            plain(obj([("row", log.latest(t, s))]))
        }
        "core.store.query_as_of" => {
            let log = Log::read(i.array("records")?)?;
            let t = i.instant("as_of")?;
            let s = i.opt("series_id").map(|_| i.str("series_id")).transpose()?;
            let from = i.opt("event_from").map(|_| i.instant("event_from"));
            let from = from.transpose()?;
            let to = i.opt("event_to").map(|_| i.instant("event_to"));
            let to = to.transpose()?;
            i.gate()?;
            log.check()?;
            check_range([Some(t), from, to].into_iter().flatten())?;
            plain(obj([("rows", log.query(t, s, from, to)?)]))
        }
        "core.store.replay" => {
            let log = Log::read(i.array("records")?)?;
            let mut points = Vec::new();
            for c in i.array("checkpoints")? {
                match c.as_str().and_then(parse_instant) {
                    Some(t) => points.push(t),
                    None => return i.fail("checkpoints", "expected instants"),
                }
            }
            i.gate()?;
            log.check()?;
            check_range(points.iter().copied())?;
            let (snapshots, head) = log.replay(&points)?;
            plain(obj([("snapshots", snapshots), ("head", head.into())]))
        }
        "core.store.snapshot" => {
            let log = Log::read(i.array("records")?)?;
            let t = i.instant("as_of")?;
            i.gate()?;
            log.check()?;
            check_range([t])?;
            let (canonical, id) = log.snapshot(t);
            plain(obj([
                ("canonical", canonical.into()),
                ("snapshot_id", id.into()),
            ]))
        }
        "core.time.business_date" => {
            let (t, z) = (i.instant("instant")?, i.zone("zone")?);
            let Some(cut) = time::parse_cutoff(i.str("cutoff")?) else {
                return i.fail("cutoff", "expected HH:MM");
            };
            let c = i.calendar("calendar")?;
            let d = time::business_date(t, z, cut, &c)?;
            plain(obj([("date", d.to_string().into())]))
        }
        "core.time.to_instant" => {
            let (z, l) = (i.zone("zone")?, i.local("local")?);
            let overlap = match i.opt("overlap").map(|_| i.str("overlap")).transpose()? {
                None => None,
                Some("EARLIER") => Some(true),
                Some("LATER") => Some(false),
                Some(_) => return i.fail("overlap", "unknown choice"),
            };
            plain(obj([("instant", time::to_instant(z, l, overlap)?.into())]))
        }
        "core.time.to_local" => {
            let (z, t) = (i.zone("zone")?, i.instant("instant")?);
            plain(obj([("local", time::to_local(z, t)?.into())]))
        }
        "core.time.utc_offset" => {
            let (z, t) = (i.zone("zone")?, i.instant("instant")?);
            plain(obj([("offset_seconds", time::utc_offset(z, t)?.into())]))
        }
        "core.ts.ar1" => {
            let x = i.reals("x")?;
            i.gate()?;
            let (c, p, s) = ts::ar1(&x)?;
            plain(obj([
                ("constant", c.into()),
                ("phi", p.into()),
                ("sigma", s.into()),
            ]))
        }
        "core.ts.autocorrelation" => {
            let (x, l) = (i.reals("x")?, i.int("max_lag")?);
            i.gate()?;
            plain(obj([("acf", ts::autocorrelation(&x, l)?.into())]))
        }
        "core.ts.ewma_variance" => {
            let (r, l) = (i.reals("returns")?, i.f64("lambda")?);
            i.gate()?;
            plain(obj([("variance", ts::ewma_variance(&r, l)?.into())]))
        }
        "core.ts.forward_fill" => {
            let (v, l) = (i.nullable_reals("values")?, i.int("limit")?);
            i.gate()?;
            plain(obj([("values", ts::forward_fill(&v, l)?.into())]))
        }
        "core.ts.ljung_box" => {
            let (x, l) = (i.reals("x")?, i.int("max_lag")?);
            i.gate()?;
            plain(obj([("statistic", ts::ljung_box(&x, l)?.into())]))
        }
        "core.ts.resample_last" => {
            let (d, v) = (i.dates("dates")?, i.nullable_reals("values")?);
            let monthly = match i.str("frequency")? {
                "WEEK" => false,
                "MONTH" => true,
                _ => return i.fail("frequency", "unknown frequency"),
            };
            i.gate()?;
            let (od, ov) = ts::resample_last(&d, &v, monthly)?;
            let od: Vec<String> = od.iter().map(ToString::to_string).collect();
            plain(obj([("dates", od.into()), ("values", ov.into())]))
        }
        "core.ts.returns" => {
            let p = i.reals("prices")?;
            let log = match i.str("kind")? {
                "SIMPLE" => false,
                "LOG" => true,
                _ => return i.fail("kind", "unknown kind"),
            };
            i.gate()?;
            plain(obj([("returns", ts::returns(&p, log)?.into())]))
        }
        "core.ts.rolling" => {
            let (x, w) = (i.reals("x")?, i.int("window")?);
            let stdev = match i.str("statistic")? {
                "MEAN" => false,
                "STDEV" => true,
                _ => return i.fail("statistic", "unknown statistic"),
            };
            i.gate()?;
            plain(obj([("values", ts::rolling(&x, w, stdev)?.into())]))
        }
        _ => crate::ops_b::dispatch(op, i),
    }
}

fn add_tenor(i: &Inputs) -> Result<Outcome> {
    let (c, d) = (i.calendar("calendar")?, i.date("date")?);
    let Some((n, unit)) = parse_tenor(i.str("tenor")?) else {
        return i.fail("tenor", "malformed tenor");
    };
    let (b, eom) = (i.bdc("convention")?, i.bool_or("end_of_month", false)?);
    let r = c.add_tenor(d, n, unit, b, eom)?;
    plain(obj([("date", r.to_string().into())]))
}

fn compounding_of(i: &Inputs) -> Result<Compounding> {
    match i.str("compounding")? {
        "SIMPLE" => Ok(Compounding::Simple),
        "CONTINUOUS" => Ok(Compounding::Continuous),
        "PERIODIC" => {
            let n = i.int("frequency")?;
            if ![1, 2, 3, 4, 6, 12].contains(&n) {
                return i.fail("frequency", "not listed");
            }
            Ok(Compounding::Periodic(n as f64))
        }
        _ => i.fail("compounding", "unknown compounding"),
    }
}

fn cos_european(i: &Inputs) -> Result<Outcome> {
    let m = Inputs::new(i.req("model")?);
    let model = match m.str("name")? {
        "BLACK_SCHOLES" => Model::BlackScholes {
            sigma: m.f64("sigma")?,
        },
        "HESTON" => Model::Heston {
            v0: m.f64("v0")?,
            kappa: m.f64("kappa")?,
            theta: m.f64("theta")?,
            sigma: m.f64("sigma")?,
            rho: m.f64("rho")?,
        },
        _ => return i.fail("model", "unknown model"),
    };
    let p = CosInputs {
        call: i.option()?,
        spot: i.f64("spot")?,
        strike: i.f64("strike")?,
        r: i.f64("r")?,
        q: i.f64("q")?,
        t: i.f64("t")?,
        model,
        terms: i.int("terms")?,
        truncation: i.f64("truncation")?,
    };
    i.gate()?;
    let (price, a, b) = cos::european(&p)?;
    Ok(Outcome {
        outputs: obj([("price", price.into())]),
        diagnostics: obj([("a", a.into()), ("b", b.into())]),
    })
}

fn data_check(i: &Inputs) -> Result<Outcome> {
    let mut quotes = Vec::new();
    for raw in i.array("quotes")? {
        if !matches!(raw, Json::Obj(_)) {
            return i.fail("quotes", "expected an object");
        }
        let q = Inputs::new(raw);
        let side = |k: &str| -> Result<Option<f64>> {
            match raw.get(k) {
                None => q.fail(k, "is required"),
                Some(_) => q.opt_f64(k),
            }
        };
        let indicative = match q.str("quote_status")? {
            "FIRM" => false,
            "INDICATIVE" => true,
            _ => return q.fail("quote_status", "must be FIRM or INDICATIVE"),
        };
        quotes.push(Quote {
            instrument_id: q.str("instrument_id")?.to_string(),
            event_time: q.instant("event_time")?,
            bid: side("bid")?,
            ask: side("ask")?,
            indicative,
        });
    }
    let mut history = HashMap::new();
    if let Some(h) = i.opt("history") {
        let Json::Obj(items) = h else {
            return i.fail("history", "expected an object");
        };
        for (k, v) in items {
            let Some(a) = v.as_array() else {
                return i.fail("history", "expected arrays");
            };
            let mids: Option<Vec<f64>> = a.iter().map(Json::as_f64).collect();
            let Some(mids) = mids else {
                return i.fail("history", "expected numbers");
            };
            history.insert(k.clone(), mids);
        }
    }
    let inputs = CheckInputs {
        as_of: i.instant("as_of")?,
        quotes,
        stale_after_seconds: i.int("stale_after_seconds")?,
        max_relative_spread: i.opt_f64("max_relative_spread")?,
        positive_only: i.bool_or("positive_only", false)?,
        outlier_threshold: i.f64_or("outlier_threshold", 5.0)?,
        outlier_min_history: i.int_or("outlier_min_history", 5)?,
        history,
    };
    i.gate()?;
    let checked = check_quotes(&inputs)?;
    let rows: Vec<Json> = checked
        .into_iter()
        .map(|c| {
            obj([
                ("instrument_id", c.instrument_id.into()),
                ("quote_status", c.quote_status.into()),
                ("quality_flags", c.quality_flags.into()),
            ])
        })
        .collect();
    plain(obj([("results", rows.into())]))
}

fn named_function(i: &Inputs) -> Result<Fun> {
    match plain_function(i.str("function")?) {
        Some(f) => Ok(f),
        None => i.fail("function", "unknown function"),
    }
}

fn diff(i: &Inputs) -> Result<Outcome> {
    let f = named_function(i)?;
    let (x, h, order) = (i.f64("x")?, i.f64("h")?, i.int("order")?);
    if order != 1 && order != 2 {
        return i.fail("order", "must be 1 or 2");
    }
    if h <= 0.0 {
        return fail("E_INPUT", "h must be positive");
    }
    let v = if order == 1 {
        (f(x + h) - f(x - h)) / (2.0 * h)
    } else {
        (f(x + h) - 2.0 * f(x) + f(x - h)) / (h * h)
    };
    plain(obj([("value", v.into())]))
}

fn integrand(i: &Inputs) -> Result<(Fun, f64, f64)> {
    Ok((named_function(i)?, i.f64("a")?, i.f64("b")?))
}

type FixedRule = fn(&dyn Fn(f64) -> f64, f64, f64, i64) -> Result<f64>;

fn fixed_rule(i: &Inputs, rule: FixedRule) -> Result<Outcome> {
    let (f, a, b) = integrand(i)?;
    let n = i.int("n")?;
    i.gate()?;
    plain(obj([("value", rule(&f, a, b, n)?.into())]))
}

fn interp_evaluate(i: &Inputs) -> Result<Outcome> {
    let method = match i.str("method")? {
        "linear" => Method::Linear,
        "log_linear" => Method::LogLinear,
        "cubic_natural" => Method::CubicNatural,
        "cubic_clamped" => Method::CubicClamped {
            start: i.f64("slope_start")?,
            end: i.f64("slope_end")?,
        },
        "cubic_not_a_knot" => Method::CubicNotAKnot,
        "monotone_pchip" => Method::Pchip,
        "tension" => Method::Tension(i.f64("tension")?),
        _ => return i.fail("method", "unknown method"),
    };
    let (x, y, at) = (i.reals("x")?, i.reals("y")?, i.reals("at")?);
    i.gate()?;
    let e = interp::evaluate(method, &x, &y, &at)?;
    plain(match e.derivatives {
        Some(d) => obj([("values", e.values.into()), ("derivatives", d.into())]),
        None => obj([("values", e.values.into())]),
    })
}

fn monte_carlo(i: &Inputs) -> Result<Outcome> {
    let method = match i.str("method")? {
        "PLAIN" => mc::Method::Plain,
        "ANTITHETIC" => mc::Method::Antithetic,
        "CONTROL_VARIATE" => mc::Method::ControlVariate,
        "SOBOL" => mc::Method::Sobol,
        _ => return i.fail("method", "unknown method"),
    };
    let p = McInputs {
        call: i.option()?,
        spot: i.f64("spot")?,
        strike: i.f64("strike")?,
        r: i.f64("r")?,
        q: i.f64("q")?,
        sigma: i.f64("sigma")?,
        t: i.f64("t")?,
        paths: i.int("paths")?,
        steps: i.int_or("steps", 1)?,
        seed: i.seed()?,
        stream: i.stream()?,
        method,
    };
    i.gate()?;
    let (price, stderr) = mc::gbm_european(&p)?;
    plain(obj([("price", price.into()), ("stderr", stderr.into())]))
}

fn pde_european(i: &Inputs) -> Result<Outcome> {
    let p = PdeInputs {
        call: i.option()?,
        spot: i.f64("spot")?,
        strike: i.f64("strike")?,
        r: i.f64("r")?,
        q: i.f64("q")?,
        sigma: i.f64("sigma")?,
        t: i.f64("t")?,
        space_steps: i.int("space_steps")?,
        time_steps: i.int("time_steps")?,
        width: i.f64_or("width", 6.0)?,
        rannacher_steps: i.int_or("rannacher_steps", 2)?,
    };
    i.gate()?;
    let r = pde::bs_european(&p)?;
    Ok(Outcome {
        outputs: obj([
            ("price", r.price.into()),
            ("delta", r.delta.into()),
            ("gamma", r.gamma.into()),
        ]),
        diagnostics: obj([("grid_h", r.grid_h.into())]),
    })
}

fn count(i: &Inputs) -> Result<i64> {
    let n = i.int("count")?;
    if n < 1 {
        return i.fail("count", "out of range");
    }
    Ok(n)
}

fn generator(i: &Inputs) -> Result<(Xoshiro, i64)> {
    let (seed, stream, n) = (i.seed()?, i.stream()?, count(i)?);
    let skip = i.int_or("skip", 0)?;
    if skip < 0 {
        return i.fail("skip", "out of range");
    }
    i.gate()?;
    let mut g = Xoshiro::seeded(seed, stream);
    for _ in 0..skip {
        g.next_u64();
    }
    Ok((g, n))
}

fn set_state(i: &Inputs) -> Result<Outcome> {
    let words = i.array("state")?;
    if words.len() != 4 {
        return i.fail("state", "expected four words");
    }
    let mut s = [0u64; 4];
    for (w, v) in s.iter_mut().zip(words) {
        *w = parse_u64(v, "state")?;
    }
    let n = count(i)?;
    i.gate()?;
    if s == [0; 4] {
        return fail("E_INPUT", "all-zero state");
    }
    let mut g = Xoshiro::from_state(s);
    let v: Vec<String> = (0..n).map(|_| g.next_u64().to_string()).collect();
    plain(obj([("values", v.into())]))
}

fn root_inputs(i: &Inputs) -> Result<(Fun, Fun, Controls)> {
    let Some((f, df)) = root_function(i.str("function")?) else {
        return i.fail("function", "unknown function");
    };
    let c = Controls {
        x_tol: i.f64_or("x_tol", 1e-12)?,
        f_tol: i.f64_or("f_tol", 0.0)?,
        max_iter: i.int_or("max_iter", 200)?,
    };
    Ok((f, df, c))
}

fn root_result(r: Root) -> Result<Outcome> {
    Ok(Outcome {
        outputs: obj([("root", r.root.into())]),
        diagnostics: obj([
            ("iterations", r.iterations.into()),
            ("residual", r.residual.into()),
            ("termination", r.termination.into()),
        ]),
    })
}
