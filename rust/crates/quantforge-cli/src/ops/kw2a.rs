//! Stage K wave 2a `risk.frtb.*` operations: FRTB DRC and RRAO (K-8a, `frtb-drc-rrao.md`) and FRTB
//! IMA (K-8f, `frtb-ima.md`). A port of `python/quantforge_core/cli/ops_k_w2a.py`. Every input is
//! read first (`E_SCHEMA`, enum values included); then the gate (the held `E_LIMIT`; `main.rs`
//! applies the finite rule after it); then the core: structural `E_INPUT` over the whole input,
//! then `E_DOMAIN` (KR-67).
use crate::input::{Inputs, schema};
use crate::ops::kw1b::choice;
use crate::ops::{Outcome, plain};
use quantforge_core::error::Result;
use quantforge_core::frtb_drc as drc;
use quantforge_core::frtb_ima as ima;
use quantforge_core::json::{Json, obj};
use std::collections::BTreeMap;

crate::ops::registry! {
(op, i)
        "risk.frtb.drc_nonsec" => drc_nonsec(i),
        "risk.frtb.drc_sec_nonctp" => drc_sec(i),
        "risk.frtb.drc_ctp" => drc_ctp(i),
        "risk.frtb.rrao" => rrao(i),
        "risk.frtb.pla" => {
            let (hpl, rtpl) = (i.reals("hpl")?, i.reals("rtpl")?);
            i.gate()?;
            let r = ima::pla(&hpl, &rtpl)?;
            plain(obj([
                ("n", (r.n as i64).into()),
                ("spearman", r.spearman.into()),
                ("ks", r.ks.into()),
                ("ks_count", (r.ks_count as i64).into()),
                ("zone", r.zone.into()),
                ("ks_pvalue_asymptotic", r.ks_pvalue_asymptotic.into()),
                ("regulatory_window", r.regulatory_window.into()),
                ("label", ima::LABEL.into()),
            ]))
        },
        "risk.frtb.pla.ks_pvalue" => {
            let (ks, n) = (i.f64("ks")?, i.int("n")?);
            i.gate()?;
            let p = ima::pla_ks_pvalue(ks, n)?;
            plain(obj([("pvalue", p.into()), ("label", ima::LABEL.into())]))
        },
        "risk.frtb.ima.lh" => lh(i),
        "risk.frtb.ima.es_lh" => {
            let es_t = i.opt("es_t").map(|_| i.reals("es_t")).transpose()?;
            let sigma = i.opt("sigma").map(|_| i.reals("sigma")).transpose()?;
            let pnl = i.opt("pnl").map(|_| i.matrix("pnl")).transpose()?;
            i.gate()?;
            let r = ima::es_lh(es_t.as_deref(), sigma.as_deref(), pnl.as_deref())?;
            plain(obj([
                ("mode", r.mode.into()),
                ("es_by_horizon", r.es_by_horizon.into()),
                ("es", r.es.into()),
                ("label", ima::LABEL.into()),
            ]))
        },
        "risk.frtb.ima.es_stressed" => {
            let t = triple(i)?;
            i.gate()?;
            let (ratio, floored, es) = ima::es_stressed(t[0], t[1], t[2])?;
            plain(obj([
                ("ratio", ratio.into()),
                ("ratio_floored", floored.into()),
                ("es", es.into()),
                ("label", ima::LABEL.into()),
            ]))
        },
        "risk.frtb.ima.imcc" => imcc(i),
        "risk.frtb.ima.ses" => {
            let a = i.reals("idio_credit")?;
            let b = i.reals("idio_equity")?;
            let c = i.reals("other")?;
            i.gate()?;
            let [x, y, z, total] = ima::ses(&a, &b, &c)?;
            plain(obj([
                ("idio_credit", x.into()),
                ("idio_equity", y.into()),
                ("other", z.into()),
                ("ses", total.into()),
                ("label", ima::LABEL.into()),
            ]))
        },
        "risk.frtb.ima.capital" => capital(i),
        "risk.frtb.rfet" => {
            let as_of = i.date("as_of")?;
            let observations = i.dates("observations")?;
            i.gate()?;
            let r = ima::rfet(as_of, &observations)?;
            let opt_count = |c: Option<usize>| c.map(|v| v as i64);
            plain(obj([
                ("window_start", r.window_start.to_string().into()),
                ("distinct_days", (r.distinct_days as i64).into()),
                ("min_window_count", opt_count(r.min_window_count).into()),
                (
                    "first_failing_window_start",
                    r.first_failing_window_start.map(|d| d.to_string()).into(),
                ),
                ("first_failing_window_count", opt_count(r.first_failing_window_count).into()),
                ("crit1", r.crit1.into()),
                ("crit2", r.crit2.into()),
                ("pass", r.pass.into()),
                ("label", ima::LABEL.into()),
            ]))
        },
        "risk.frtb.rfet.bucket" => {
            let row = choice(i, "row", &["A", "B", "C", "D"])?;
            let (t, delta) = (i.opt_f64("t")?, i.opt_f64("delta")?);
            i.gate()?;
            let (b, lower, upper) = ima::rfet_bucket(&row, t, delta)?;
            plain(obj([
                ("bucket", (b as i64).into()),
                ("lower", lower.into()),
                ("upper", upper.into()),
                ("label", ima::LABEL.into()),
            ]))
        },
}

const ZONES: [&str; 2] = ["GREEN", "AMBER"];

fn objects<'a>(i: &Inputs<'a>, k: &str) -> Result<Vec<Inputs<'a>>> {
    i.array(k)?
        .iter()
        .map(|v| match v {
            Json::Obj(_) => Ok(Inputs::new(v)),
            _ => i.fail(k, "must hold objects"),
        })
        .collect()
}

fn object<'a>(i: &Inputs<'a>, k: &str) -> Result<Inputs<'a>> {
    match i.req(k)? {
        v @ Json::Obj(_) => Ok(Inputs::new(v)),
        _ => i.fail(k, "not an object"),
    }
}

fn string(i: &Inputs, k: &str) -> Result<String> {
    i.str(k).map(str::to_string)
}

fn triple(t: &Inputs) -> Result<[f64; 3]> {
    Ok([t.f64("es_rs")?, t.f64("es_fc")?, t.f64("es_rc")?])
}

fn drc_nonsec(i: &Inputs) -> Result<Outcome> {
    let positions = objects(i, "positions")?
        .iter()
        .map(|p| {
            Ok(drc::Position {
                id: string(p, "id")?,
                obligor: string(p, "obligor")?,
                bucket: choice(p, "bucket", &drc::BUCKETS)?,
                seniority: choice(p, "seniority", &drc::SENIORITIES)?,
                notional: p.f64("notional")?,
                market_value: p.f64("market_value")?,
                maturity_years: p.f64("maturity_years")?,
                cash_equity: p.bool_or("cash_equity", false)?,
                lgd_applies: p.bool_or("lgd_applies", true)?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    let r = object(i, "ratings")?;
    let Json::Obj(names) = r.0 else {
        return i.fail("ratings", "not an object");
    };
    let mut ratings = BTreeMap::new();
    for (name, _) in names {
        // A `null` rating is absent in the reference reader, so it is `E_SCHEMA` there too.
        ratings.insert(name.clone(), choice(&r, name, &drc::RATINGS)?);
    }
    i.gate()?;
    let out = drc::drc_nonsec(&positions, &ratings)?;
    let positions = out
        .positions
        .iter()
        .map(|p| {
            obj([
                ("id", p.id.as_str().into()),
                ("gross_jtd", p.gross_jtd.into()),
                ("weight", p.weight.into()),
                ("scaled_jtd", p.scaled_jtd.into()),
            ])
        })
        .collect();
    let obligors = out
        .obligors
        .iter()
        .map(|o| {
            obj([
                ("obligor", o.obligor.as_str().into()),
                ("net_long", o.net_long.into()),
                ("net_short", o.net_short.into()),
                ("rw", o.rw.into()),
            ])
        })
        .collect();
    plain(obj([
        ("positions", Json::Arr(positions)),
        ("obligors", Json::Arr(obligors)),
        ("buckets", buckets(&out.buckets)),
        ("drc", out.drc.into()),
        ("label", drc::LABEL.into()),
    ]))
}

fn buckets(rows: &[drc::BucketRow]) -> Json {
    Json::Arr(
        rows.iter()
            .map(|b| {
                obj([
                    ("bucket", b.bucket.as_str().into()),
                    ("hbr", b.hbr.into()),
                    ("wtd_long", b.wtd_long.into()),
                    ("wtd_short", b.wtd_short.into()),
                    ("drc", b.drc.into()),
                ])
            })
            .collect(),
    )
}

/// The `positions` output of the securitisation and CTP verbs (no gross JTD).
fn scaled_rows(rows: &[drc::PositionRow]) -> Json {
    Json::Arr(
        rows.iter()
            .map(|p| {
                obj([
                    ("id", p.id.as_str().into()),
                    ("weight", p.weight.into()),
                    ("scaled_jtd", p.scaled_jtd.into()),
                ])
            })
            .collect(),
    )
}

fn drc_sec(i: &Inputs) -> Result<Outcome> {
    let positions = objects(i, "positions")?
        .iter()
        .map(|p| {
            Ok(drc::SecPosition {
                id: string(p, "id")?,
                bucket: string(p, "bucket")?,
                pool: string(p, "pool")?,
                tranche: string(p, "tranche")?,
                market_value: p.f64("market_value")?,
                maturity_years: p.f64("maturity_years")?,
                rw: p.f64("rw")?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    i.gate()?;
    let out = drc::drc_sec_nonctp(&positions)?;
    plain(obj([
        ("positions", scaled_rows(&out.positions)),
        ("buckets", buckets(&out.buckets)),
        ("drc", out.drc.into()),
        ("label", drc::LABEL.into()),
        ("rw_source", drc::RW_SOURCE.into()),
    ]))
}

fn drc_ctp(i: &Inputs) -> Result<Outcome> {
    let positions = match i.opt("positions") {
        None => None,
        Some(_) => Some(
            objects(i, "positions")?
                .iter()
                .map(|p| {
                    Ok(drc::CtpPosition {
                        id: string(p, "id")?,
                        index: string(p, "index")?,
                        series: string(p, "series")?,
                        tranche: string(p, "tranche")?,
                        market_value: p.f64("market_value")?,
                        maturity_years: p.f64("maturity_years")?,
                        rw: p.f64("rw")?,
                    })
                })
                .collect::<Result<Vec<_>>>()?,
        ),
    };
    let bucket_drc = i
        .opt("bucket_drc")
        .map(|_| i.reals("bucket_drc"))
        .transpose()?;
    i.gate()?;
    let out = drc::drc_ctp(positions.as_deref(), bucket_drc.as_deref())?;
    let Some(rows) = &out.positions else {
        return plain(obj([
            ("drc", out.drc.into()),
            ("label", drc::LABEL.into()),
            ("rw_source", drc::RW_SOURCE.into()),
        ]));
    };
    let ctp_buckets = out
        .buckets
        .iter()
        .map(|b| {
            obj([
                ("bucket", b.bucket.as_str().into()),
                ("wtd_long", b.wtd_long.into()),
                ("wtd_short", b.wtd_short.into()),
                ("drc", b.drc.into()),
            ])
        })
        .collect();
    plain(obj([
        ("positions", scaled_rows(rows)),
        ("hbr_ctp", out.hbr_ctp.into()),
        ("buckets", Json::Arr(ctp_buckets)),
        ("drc", out.drc.into()),
        ("label", drc::LABEL.into()),
        ("rw_source", drc::RW_SOURCE.into()),
    ]))
}

fn rrao(i: &Inputs) -> Result<Outcome> {
    let instruments = objects(i, "instruments")?
        .iter()
        .map(|x| {
            Ok(drc::Instrument {
                id: string(x, "id")?,
                gross_notional: x.f64("gross_notional")?,
                kind: choice(x, "kind", &drc::KINDS)?,
                listed_or_clearable: x.bool("listed_or_clearable")?,
                back_to_back: x.bool("back_to_back")?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    i.gate()?;
    let out = drc::rrao(&instruments)?;
    let rows = out
        .instruments
        .iter()
        .map(|r| {
            obj([
                ("id", r.id.as_str().into()),
                ("weight", r.weight.into()),
                ("excluded", r.excluded.into()),
                ("addon", r.addon.into()),
            ])
        })
        .collect();
    plain(obj([
        ("instruments", Json::Arr(rows)),
        ("rrao", out.rrao.into()),
        ("label", drc::LABEL.into()),
    ]))
}

/// `AAA/BBB`: three capital letters, a slash, three capital letters.
fn fx_pair_form(s: &str) -> bool {
    let b = s.as_bytes();
    b.len() == 7 && b[3] == b'/' && b[..3].iter().chain(&b[4..]).all(u8::is_ascii_uppercase)
}

fn lh(i: &Inputs) -> Result<Outcome> {
    let categories: Vec<&str> = ima::LH_TABLE.iter().map(|r| r.0).collect();
    let category = i
        .opt("category")
        .map(|_| choice(i, "category", &categories))
        .transpose()?;
    let fx_pair = match i.opt("fx_pair") {
        None => None,
        Some(_) => {
            let p = string(i, "fx_pair")?;
            if !fx_pair_form(&p) {
                return Err(schema("fx_pair", "not of the form AAA/BBB"));
            }
            Some(p)
        }
    };
    let constituents = match i.opt("constituents") {
        None => None,
        Some(_) => Some(
            objects(i, "constituents")?
                .iter()
                .map(|c| Ok((c.f64("weight")?, c.int("n")?)))
                .collect::<Result<Vec<_>>>()?,
        ),
    };
    let maturity = i.opt_f64("maturity_days")?;
    i.gate()?;
    let r = ima::liquidity_horizon(
        category.as_deref(),
        fx_pair.as_deref(),
        constituents.as_deref(),
        maturity,
    )?;
    plain(obj([
        ("n", r.n.into()),
        ("table_n", r.table_n.into()),
        ("rule", r.rule.into()),
        ("label", ima::LABEL.into()),
    ]))
}

fn imcc(i: &Inputs) -> Result<Outcome> {
    let portfolio = triple(&object(i, "portfolio")?)?;
    let c = object(i, "classes")?;
    let Json::Obj(keys) = c.0 else {
        return i.fail("classes", "not an object");
    };
    if let Some((key, _)) = keys
        .iter()
        .find(|(k, _)| !ima::IMCC_CLASSES.contains(&k.as_str()))
    {
        return Err(schema(
            &format!("classes.{key}"),
            "not a risk class (IR, EQ, FX, COM, CS)",
        ));
    }
    let classes = keys
        .iter()
        .map(|(k, _)| Ok((k.clone(), triple(&object(&c, k)?)?)))
        .collect::<Result<Vec<_>>>()?;
    i.gate()?;
    let r = ima::imcc(portfolio, &classes)?;
    let per = Json::Obj(
        r.classes
            .iter()
            .map(|(k, v)| ((*k).to_string(), (*v).into()))
            .collect(),
    );
    let floored: Vec<Json> = r.classes_floored.iter().map(|k| (*k).into()).collect();
    plain(obj([
        ("imcc_c", r.imcc_c.into()),
        ("portfolio_floored", r.portfolio_floored.into()),
        ("classes", per),
        ("classes_floored", Json::Arr(floored)),
        ("imcc", r.imcc.into()),
        ("label", ima::LABEL.into()),
    ]))
}

fn capital(i: &Inputs) -> Result<Outcome> {
    let desks = objects(i, "desks")?
        .iter()
        .map(|d| Ok((choice(d, "zone", &ZONES)?, d.f64("sa")?)))
        .collect::<Result<Vec<_>>>()?;
    let x = ima::CapitalInputs {
        imcc_prev: i.f64("imcc_prev")?,
        ses_prev: i.f64("ses_prev")?,
        imcc_avg: i.f64("imcc_avg")?,
        ses_avg: i.f64("ses_avg")?,
        exceptions: i.int("exceptions")?,
        drc: i.f64("drc")?,
        desks,
        c_u: i.f64("c_u")?,
        sa_all: i.f64("sa_all")?,
        qualitative_addon: i.f64_or("qualitative_addon", 0.0)?,
    };
    i.gate()?;
    let r = ima::capital(&x)?;
    plain(obj([
        ("m_c", r.m_c.into()),
        ("c_a", r.c_a.into()),
        ("ima_ga", r.ima_ga.into()),
        ("sa_ga", r.sa_ga.into()),
        ("k", r.k.into()),
        ("surcharge", r.surcharge.into()),
        ("acr_total", r.acr_total.into()),
        ("label", ima::LABEL.into()),
    ]))
}
