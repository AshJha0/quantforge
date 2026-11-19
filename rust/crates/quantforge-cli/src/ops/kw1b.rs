//! Stage K wave 1b `risk.*` operations: SA-CCR (K-8d, `sa-ccr.md`) and FRTB IMA backtesting
//! (K-8e, `frtb-ima-backtest.md`). Every input is read (`E_SCHEMA`, enum values included) before
//! the gate; the core then applies the finite rule, structure (`E_INPUT`) and domain (`E_DOMAIN`),
//! the HR-122 order. Paths are absolute (`crate::ops::...`) so the file compiles both where it is
//! included now (a test-only `#[path]` module in `main.rs`) and as `ops::kw1b` once the coordinator
//! registers it (`program/STAGE_K_W1B_PORTS_HANDOVER.md`).
use crate::input::Inputs;
use crate::ops::{Outcome, plain};
use quantforge_core::error::Result;
use quantforge_core::frtb_backtest as fb;
use quantforge_core::json::{Json, obj};
use quantforge_core::saccr;

crate::ops::registry! {
(op, i)
        "risk.saccr.ead" => saccr_ead(i),
        "risk.frtb.backtest.zone" => {
            let n = i.int("observations")?;
            let (a, h) = (i.int("exceptions_actual")?, i.int("exceptions_hypothetical")?);
            i.gate()?;
            let z = fb::zone(n, a, h)?;
            plain(obj([
                ("exceptions", z.exceptions.into()),
                ("cumulative_probability", z.cumulative_probability.into()),
                ("zone", z.zone.into()),
                ("amber_from", z.amber_from.into()),
                ("red_from", z.red_from.into()),
                ("multiplier", z.multiplier.into()),
            ]))
        },
        "risk.frtb.backtest.desk" => {
            let n = i.int("observations")?;
            let counts = [
                i.int("exceptions_99_actual")?,
                i.int("exceptions_99_hypothetical")?,
                i.int("exceptions_975_actual")?,
                i.int("exceptions_975_hypothetical")?,
            ];
            i.gate()?;
            let d = fb::desk(n, counts)?;
            plain(obj([
                ("exceptions_99", d.exceptions_99.into()),
                ("exceptions_975", d.exceptions_975.into()),
                ("cumulative_probability_99", d.cumulative_probability_99.into()),
                ("cumulative_probability_975", d.cumulative_probability_975.into()),
                ("breach_99", d.breach_99.into()),
                ("breach_975", d.breach_975.into()),
                ("eligible", d.eligible.into()),
            ]))
        },
        "risk.frtb.backtest.count" => {
            let var = i.nullable_reals("var")?;
            let actual = i.nullable_reals("actual")?;
            let hypothetical = i.nullable_reals("hypothetical")?;
            i.gate()?;
            let c = fb::count_exceptions(&var, &actual, &hypothetical)?;
            plain(obj([
                ("observations", c.observations.into()),
                ("exceptions_actual", c.exceptions_actual.into()),
                ("exceptions_hypothetical", c.exceptions_hypothetical.into()),
                ("exceptions", c.exceptions.into()),
                ("days_actual", c.days_actual.into()),
                ("days_hypothetical", c.days_hypothetical.into()),
            ]))
        },
}

const KINDS: [&str; 3] = ["LINEAR", "OPTION", "CDO"];
const POSITIONS: [&str; 4] = ["LONG", "SHORT", "BOUGHT", "SOLD"];
const OPTION_TYPES: [&str; 2] = ["CALL", "PUT"];
const SUBCLASSES: [&str; 16] = [
    "AAA",
    "AA",
    "A",
    "BBB",
    "BB",
    "B",
    "CCC",
    "IG",
    "SG",
    "SINGLE",
    "INDEX",
    "ELECTRICITY",
    "OIL_GAS",
    "METALS",
    "AGRICULTURAL",
    "OTHER",
];

/// A string from a fixed list; a value outside it is `E_SCHEMA` (ruling KR-39).
pub(crate) fn choice(i: &Inputs, k: &str, allowed: &[&str]) -> Result<String> {
    let s = i.str(k)?;
    if allowed.contains(&s) {
        Ok(s.to_string())
    } else {
        i.fail(k, "value not in the allowed list")
    }
}

fn opt_choice(i: &Inputs, k: &str, allowed: &[&str]) -> Result<Option<String>> {
    i.opt(k).map(|_| choice(i, k, allowed)).transpose()
}

fn opt_string(i: &Inputs, k: &str) -> Result<Option<String>> {
    i.opt(k).map(|_| i.str(k).map(str::to_string)).transpose()
}

fn objects<'a>(i: &Inputs<'a>, k: &str) -> Result<Vec<Inputs<'a>>> {
    i.array(k)?
        .iter()
        .map(|v| match v {
            Json::Obj(_) => Ok(Inputs::new(v)),
            _ => i.fail(k, "expected objects"),
        })
        .collect()
}

fn trade(t: &Inputs) -> Result<saccr::Trade> {
    Ok(saccr::Trade {
        id: t.str("id")?.to_string(),
        asset_class: choice(t, "asset_class", &saccr::CLASSES)?,
        notional: t.f64("notional")?,
        market_value: t.f64("market_value")?,
        maturity: t.f64("maturity")?,
        kind: opt_choice(t, "kind", &KINDS)?.unwrap_or_else(|| "LINEAR".to_string()),
        position: choice(t, "position", &POSITIONS)?,
        treatment: opt_choice(t, "treatment", &saccr::TREATMENTS)?
            .unwrap_or_else(|| "NORMAL".to_string()),
        start: t.opt_f64("start")?,
        end: t.opt_f64("end")?,
        hedging_set: opt_string(t, "hedging_set")?,
        entity: opt_string(t, "entity")?,
        subclass: opt_choice(t, "subclass", &SUBCLASSES)?,
        option_type: opt_choice(t, "option_type", &OPTION_TYPES)?,
        underlying_price: t.opt_f64("underlying_price")?,
        strike: t.opt_f64("strike")?,
        exercise: t.opt_f64("exercise")?,
        shift: t.f64_or("shift", 0.0)?,
        attachment: t.opt_f64("attachment")?,
        detachment: t.opt_f64("detachment")?,
    })
}

fn saccr_ead(i: &Inputs) -> Result<Outcome> {
    let trades = objects(i, "trades")?
        .iter()
        .map(trade)
        .collect::<Result<Vec<_>>>()?;
    let margin = match i.opt("margin") {
        None => None,
        Some(Json::Obj(_)) => {
            let m = Inputs::new(i.req("margin")?);
            Some(saccr::Margin {
                threshold: m.f64("threshold")?,
                mta: m.f64("mta")?,
                nica: m.f64("nica")?,
                remargin_days: m.int("remargin_days")?,
                mpor_days: m.opt_int("mpor_days")?,
                illiquid: m.bool_or("illiquid", false)?,
                disputes: m.bool_or("disputes", false)?,
            })
        }
        Some(_) => return i.fail("margin", "expected an object"),
    };
    let collateral = i.f64_or("collateral", 0.0)?;
    let ir_offset = i.bool_or("ir_offset", true)?;
    i.gate()?;
    plain(saccr_outputs(&saccr::ead(
        &trades,
        collateral,
        margin.as_ref(),
        ir_offset,
    )?))
}

/// The outputs of `risk.saccr.ead`, in the contract's order.
pub(crate) fn saccr_outputs(r: &saccr::EadResult) -> Json {
    let addon = Json::Obj(
        saccr::CLASSES
            .iter()
            .zip(r.addon)
            .map(|(k, v)| ((*k).to_string(), v.into()))
            .collect(),
    );
    let sets = r
        .hedging_sets
        .iter()
        .map(|h| {
            obj([
                ("asset_class", h.asset_class.into()),
                ("treatment", h.treatment.into()),
                ("key", h.key.as_str().into()),
                ("addon", h.addon.into()),
            ])
        })
        .collect();
    let trades = r
        .trades
        .iter()
        .map(|t| {
            obj([
                ("id", t.id.as_str().into()),
                ("supervisory_duration", t.supervisory_duration.into()),
                ("adjusted_notional", t.adjusted_notional.into()),
                ("maturity_factor", t.maturity_factor.into()),
                ("delta", t.delta.into()),
                ("effective_notional", t.effective_notional.into()),
                ("supervisory_factor", t.supervisory_factor.into()),
            ])
        })
        .collect();
    obj([
        ("ead", r.ead.into()),
        ("rc", r.rc.into()),
        ("pfe", r.pfe.into()),
        ("multiplier", r.multiplier.into()),
        ("addon_aggregate", r.addon_aggregate.into()),
        ("addon", addon),
        ("v", r.v.into()),
        ("c", r.c.into()),
        ("margined", r.margined.into()),
        ("mpor_days", r.mpor_days.into()),
        ("ead_unmargined", r.ead_unmargined.into()),
        ("capped", r.capped.into()),
        ("hedging_sets", Json::Arr(sets)),
        ("trades", Json::Arr(trades)),
    ])
}

#[cfg(test)]
mod tests {
    use super::{NAMES, choice, dispatch};
    use crate::input::Inputs;
    use quantforge_core::error::{QfError, err};
    use quantforge_core::json::{Json, parse};

    /// `run_operation` of `main.rs` with this module's dispatcher: `E_SCHEMA`, then the held
    /// `E_LIMIT`, then the finite rule, then the operation's own checks.
    fn run(op: &str, inputs: &Json) -> Result<Json, QfError> {
        let inputs = &crate::with_non_finite_tokens(inputs);
        let limit = crate::limits::check(op, inputs);
        let result = dispatch(op, &Inputs(inputs, limit.clone())).expect("a wave 1b operation");
        match (result, limit) {
            (Err(e), _) if e.code == "E_SCHEMA" => Err(e),
            (_, Some(l)) => Err(l),
            _ if inputs.has_non_finite() => Err(err("E_DOMAIN", "a Real input is NaN or infinite")),
            (r, None) => r.map(|o| o.outputs),
        }
    }

    fn tolerance(class: &str) -> Option<(f64, f64)> {
        match class {
            "simple_analytic" => Some((1e-12, 1e-10)),
            "date_and_convention" | "bit_exact" => None,
            other => panic!("class {other} not used by these suites"),
        }
    }

    fn same(a: &Json, e: &Json, tol: Option<(f64, f64)>, path: &str) -> Option<String> {
        match e {
            Json::Obj(o) => o.iter().find_map(|(k, ev)| match a.get(k) {
                Some(av) => same(av, ev, tol, &format!("{path}.{k}")),
                None => Some(format!("{path}.{k} missing")),
            }),
            Json::Arr(x) => match a.as_array() {
                Some(y) if y.len() == x.len() => x
                    .iter()
                    .zip(y)
                    .enumerate()
                    .find_map(|(n, (ev, av))| same(av, ev, tol, &format!("{path}[{n}]"))),
                _ => Some(format!("{path} length")),
            },
            Json::Int(_) | Json::Num(_) => {
                let (Some(x), Some(y)) = (a.as_f64(), e.as_f64()) else {
                    return Some(format!("{path} not a number"));
                };
                let ok = match tol {
                    None => x == y,
                    Some((ab, re)) => (x - y).abs() <= ab + re * x.abs().max(y.abs()),
                };
                (!ok).then(|| format!("{path}: {x} vs {y}"))
            }
            _ => (a != e).then(|| format!("{path}: {} vs {}", a.to_text(), e.to_text())),
        }
    }

    /// Replays one suite: every case, value and error, with the case's own tolerance classes.
    fn suite(name: &str) -> usize {
        let path = format!(
            "{}/../../../datasets/golden/stage_k/{name}.json",
            env!("CARGO_MANIFEST_DIR")
        );
        let text = std::fs::read_to_string(path).expect("golden file");
        let (doc, _) = parse(&text).expect("golden JSON");
        let cases = doc.get("cases").and_then(Json::as_array).expect("cases");
        let mut failures = Vec::new();
        let mut two_errors = 0;
        for c in cases {
            let id = c.get("case_id").and_then(Json::as_str).unwrap_or("?");
            let op = c
                .get("operation")
                .and_then(Json::as_str)
                .expect("operation");
            let inputs = c.get("inputs").expect("inputs");
            let got = if NAMES.contains(&op) {
                run(op, inputs)
            } else {
                // tlk_k: the stage F operation, through the registered dispatcher.
                crate::ops::dispatch(op, &Inputs::new(inputs)).map(|o| o.outputs)
            };
            let expected = c.get("expected").expect("expected");
            if c.get("description")
                .and_then(Json::as_str)
                .is_some_and(|d| d.contains("two errors"))
            {
                two_errors += 1;
            }
            let problem = match (expected.get("status").and_then(Json::as_str), &got) {
                (Some("error"), Err(e)) => {
                    let want = expected.get("error_code").and_then(Json::as_str);
                    (want != Some(e.code)).then(|| format!("{id}: {} vs {want:?}", e.code))
                }
                (Some("ok"), Ok(out)) => {
                    let base = c
                        .get("tolerance_class")
                        .and_then(Json::as_str)
                        .unwrap_or("bit_exact");
                    let classes = c.get("output_classes");
                    let want = expected.get("outputs").expect("outputs");
                    let Json::Obj(keys) = want else {
                        panic!("outputs object")
                    };
                    keys.iter().find_map(|(k, ev)| {
                        let cls = classes
                            .and_then(|o| o.get(k))
                            .and_then(Json::as_str)
                            .unwrap_or(base);
                        match out.get(k) {
                            Some(av) => same(av, ev, tolerance(cls), &format!("{id}.{k}")),
                            None => Some(format!("{id}.{k} missing")),
                        }
                    })
                }
                (s, g) => Some(format!("{id}: status {s:?} vs {g:?}")),
            };
            failures.extend(problem);
        }
        assert!(
            failures.is_empty(),
            "{} failures: {failures:?}",
            failures.len()
        );
        two_errors
    }

    #[test]
    fn saccr_goldens() {
        assert!(suite("saccr_k") >= 1);
    }

    #[test]
    fn backtest_goldens() {
        assert!(suite("btk_k") >= 1);
    }

    #[test]
    fn traffic_light_outside_check() {
        suite("tlk_k");
    }

    #[test]
    fn verbs_are_registered() {
        // Registered in ops/mod.rs DOMAINS at integration (stage K round 1).
        for op in NAMES {
            assert!(crate::ops::operations().contains(op), "{op}");
        }
        assert!(dispatch("risk.none", &Inputs::new(&Json::Null)).is_none());
    }

    fn code(op: &str, text: &str) -> &'static str {
        run(op, &parse(text).expect("json").0)
            .expect_err("an error")
            .code
    }

    #[test]
    fn input_layer_order() {
        let t = r#"{"trades":[{"id":"a","asset_class":"FX","notional":0,"market_value":0,"maturity":1,"position":"LONG","hedging_set":"X","kind":"SWAP"}]}"#;
        assert_eq!(code("risk.saccr.ead", t), "E_SCHEMA");
        let t = r#"{"trades":[{"id":"a","asset_class":"FX","notional":"NaN","market_value":0,"maturity":1,"position":"LONG"}]}"#;
        assert_eq!(code("risk.saccr.ead", t), "E_DOMAIN");
        let t = r#"{"trades":[{"id":"a","asset_class":"FX","notional":1,"market_value":0,"maturity":1,"position":"LONG","hedging_set":"X"}],"margin":3}"#;
        assert_eq!(code("risk.saccr.ead", t), "E_SCHEMA");
        let t = r#"{"observations":1000001,"exceptions_99_actual":-1,"exceptions_99_hypothetical":0,"exceptions_975_actual":0,"exceptions_975_hypothetical":0}"#;
        assert_eq!(code("risk.frtb.backtest.desk", t), "E_LIMIT");
        let t = r#"{"trades":[{"id":"o","asset_class":"EQUITY","notional":10,"market_value":1,"maturity":1,"position":"SOLD","kind":"OPTION","option_type":"PUT","underlying_price":1,"strike":1,"exercise":1,"shift":0.5,"entity":"E","subclass":"INDEX","treatment":"NORMAL"}],"collateral":1,"ir_offset":false,"margin":{"threshold":0,"mta":0,"nica":0,"remargin_days":1,"mpor_days":12,"illiquid":false,"disputes":false}}"#;
        let out = run("risk.saccr.ead", &parse(t).expect("json").0).expect("ok");
        assert_eq!(out.get("mpor_days"), Some(&Json::Int(12)));
        let v = parse(r#"{"k":"Z"}"#).expect("json").0;
        assert!(choice(&Inputs::new(&v), "k", &["A"]).is_err());
    }
}
